// SPDX-License-Identifier: GPL-2.0-only
/*
 * Controlled T6001 UID1 / fixed DSB-decrypt experiment. NOT a general AES driver.
 * Probe/status do not read/write AES registers or submit operations.
 * After explicit SELFTEST starts a session, retain module/PM/DMA until reset,
 * including on success. No cancellation, reset, stop, or post-session teardown.
 * Supplier removal, DT removal, kexec and system sleep are outside this workflow.
 */
#include <crypto/hash.h>
#include <crypto/skcipher.h>
#include <crypto/utils.h>
#include <linux/capability.h>
#include <linux/compat.h>
#include <linux/completion.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/irq.h>
#include <linux/irqdomain.h>
#include <linux/io.h>
#include <linux/iommu.h>
#include <linux/iopoll.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/scatterlist.h>
#include <linux/slab.h>
#include <linux/suspend.h>
#include <linux/uaccess.h>
#include <linux/unaligned.h>
#include "omvm_uid1_uapi.h"

static bool j314c_irq_diagnostic;
module_param(j314c_irq_diagnostic, bool, 0400);
MODULE_PARM_DESC(j314c_irq_diagnostic,
	"Explicit J314c-only AIC2 mapping when DT IRQ is absent; retained until reset");

#define AES_CONTROL 0x08
#define AES_READY 0x0c
#define AES_IRQ_STATUS 0x18
#define AES_IRQ_MASK 0x1c
#define AES_WATERMARK 0x20
#define AES_FIFO_STATUS 0x24
#define AES_TAG_STATUS 0x30
#define AES_FIFO 0x200
#define AES_READY_MASK 0x3f80
#define AES_ERROR_MASK 0x3efde
#define AES_INTERRUPT_MASK 0x3effe
#define AES_COMPLETE BIT(5)
#define AES_READS_PENDING 0xff00
#define AES_FIFO_WORDS 128
#define AES_REQUEST_TIMEOUT_MS 1000
#define AES_TAG_TIMEOUT_US 20000

/* Public known-answer test: NIST SP800-38A Appendix F.2.1, first block.
 * https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38a.pdf
 * This fixed software key is ONLY a hardware transport test, never a fallback.
 */
static const u8 kat_key[16] = {
	0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
	0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c,
};
static const u8 kat_iv[16] = {
	0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
	0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,
};
static const u8 kat_plain[16] = {
	0x6b, 0xc1, 0xbe, 0xe2, 0x2e, 0x40, 0x9f, 0x96,
	0xe9, 0x3d, 0x7e, 0x11, 0x73, 0x93, 0x17, 0x2a,
};
static const u8 kat_cipher[16] = {
	0x76, 0x49, 0xab, 0xac, 0x81, 0x19, 0xb2, 0x46,
	0xce, 0xe9, 0x8e, 0x9b, 0x12, 0xe9, 0x19, 0x7d,
};
static const u8 bundle_digest[32] = {
	0x1c, 0x6a, 0x5c, 0xc4, 0x1f, 0x94, 0x1e, 0x07,
	0x88, 0xe4, 0x36, 0x14, 0x8f, 0x28, 0x0d, 0xd5,
	0xa8, 0x75, 0xca, 0xf5, 0x79, 0x29, 0x81, 0x1b,
	0x80, 0x2a, 0xad, 0xca, 0x9e, 0x25, 0x3c, 0x8d,
};

struct uid1_provider {
	struct device *dev;
	void __iomem *engine;
	void __iomem *disable;
	struct miscdevice misc;
	struct mutex op_lock;
	spinlock_t state_lock;
	struct completion done;
	struct notifier_block pm_notifier;
	struct crypto_shash *sha;
	struct crypto_skcipher *cbc[2];
	void *src, *dst, *iv_result;
	dma_addr_t src_dma, dst_dma, iv_dma;
	int irq;
	int result;
	int last_errno;
	u32 state, hw_status, hw_tag, completed_ops;
	u8 expected_tag;
	bool busy, active, pm_transition;
	bool pinned, power_held, engine_started, irq_enabled;
};

static bool uid1_admin(void)
{
	return uid_eq(current_euid(), GLOBAL_ROOT_UID) &&
		capable(CAP_SYS_RAWIO);
}

static void uid1_poison(struct uid1_provider *a, int error)
{
	unsigned long flags;

	spin_lock_irqsave(&a->state_lock, flags);
	a->state = OMVM_UID1_POISONED;
	a->last_errno = error;
	a->result = error;
	a->active = false;
	spin_unlock_irqrestore(&a->state_lock, flags);
	complete(&a->done);
}

static bool uid1_poisoned(struct uid1_provider *a)
{
	return READ_ONCE(a->state) == OMVM_UID1_POISONED;
}

static void uid1_irq_disable(struct uid1_provider *a)
{
	/* Only op_lock owner changes irq_enabled. Never called by IRQ thread. */
	if (a->irq_enabled) {
		disable_irq(a->irq);
		a->irq_enabled = false;
	}
}

static irqreturn_t uid1_irq_thread(int irq, void *data)
{
	struct uid1_provider *a = data;
	unsigned long flags;
	u32 status, tag = 0, after;
	u8 expected;
	bool active;
	int ret;

	(void)irq;
	if (!READ_ONCE(a->power_held))
		return IRQ_NONE;
	status = readl(a->engine + AES_IRQ_STATUS);
	writel(status, a->engine + AES_IRQ_STATUS);
	spin_lock_irqsave(&a->state_lock, flags);
	a->hw_status |= status;
	active = a->active;
	expected = a->expected_tag;
	spin_unlock_irqrestore(&a->state_lock, flags);
	if (status & AES_ERROR_MASK) {
		uid1_poison(a, -EIO);
		return IRQ_HANDLED;
	}
	if (!(status & AES_COMPLETE) || !active || uid1_poisoned(a))
		return status ? IRQ_HANDLED : IRQ_NONE;

	/* Threaded, finite wait; never reproduce native's unbounded IRQ spin. */
	ret = readl_poll_timeout(a->engine + AES_TAG_STATUS, tag,
				!(tag & AES_READS_PENDING), 10,
				AES_TAG_TIMEOUT_US);
	after = readl(a->engine + AES_IRQ_STATUS);
	writel(after, a->engine + AES_IRQ_STATUS);
	spin_lock_irqsave(&a->state_lock, flags);
	a->hw_tag = tag;
	a->hw_status |= after;
	spin_unlock_irqrestore(&a->state_lock, flags);
	if (ret || (after & AES_ERROR_MASK) || tag == U32_MAX ||
	    (tag & 0xff) != expected) {
		uid1_poison(a, ret ? ret : -EIO);
		return IRQ_HANDLED;
	}
	dma_rmb();
	spin_lock_irqsave(&a->state_lock, flags);
	if (a->active && a->state != OMVM_UID1_POISONED) {
		a->result = 0;
		a->active = false;
		a->completed_ops++;
	}
	spin_unlock_irqrestore(&a->state_lock, flags);
	complete(&a->done);
	return IRQ_HANDLED;
}

static bool uid1_dma_range_ok(dma_addr_t address, size_t size)
{
	return size && size <= U32_MAX &&
		address <= (dma_addr_t)U32_MAX - (size - 1);
}

static void uid1_free_dma_before_session(struct uid1_provider *a)
{
	/* Called only before permanent pin/power/hardware session. */
	if (a->iv_result)
		dma_free_coherent(a->dev, 16, a->iv_result, a->iv_dma);
	if (a->dst)
		dma_free_coherent(a->dev, 16, a->dst, a->dst_dma);
	if (a->src)
		dma_free_coherent(a->dev, 16, a->src, a->src_dma);
	a->iv_result = a->dst = a->src = NULL;
}

static int uid1_alloc_dma(struct uid1_provider *a)
{
	if (a->src)
		return 0;
	a->src = dma_alloc_coherent(a->dev, 16, &a->src_dma, GFP_KERNEL);
	a->dst = dma_alloc_coherent(a->dev, 16, &a->dst_dma, GFP_KERNEL);
	a->iv_result = dma_alloc_coherent(a->dev, 16, &a->iv_dma, GFP_KERNEL);
	if (!a->src || !a->dst || !a->iv_result ||
	    !uid1_dma_range_ok(a->src_dma, 16) ||
	    !uid1_dma_range_ok(a->dst_dma, 16) ||
	    !uid1_dma_range_ok(a->iv_dma, 16)) {
		uid1_free_dma_before_session(a);
		return -ENOMEM;
	}
	return 0;
}

static int uid1_check_ready(struct uid1_provider *a, bool require_uid1)
{
	u32 value;
	int ret;

	ret = readl_poll_timeout(a->engine + AES_READY, value,
		value != U32_MAX && (value & AES_READY_MASK) == AES_READY_MASK,
		25000, 5000000);
	if (ret)
		return ret;
	if (require_uid1) {
		value = readl(a->disable);
		if (value == U32_MAX || (value & BIT(0)))
			return -ENOKEY;
	}
	return 0;
}

/* Caller owns op_lock and normal runtime power. No FIFO/IRQ/DMA activity. */
static int uid1_sample_capability(struct uid1_provider *a,
				  struct omvm_uid1_capability *capability)
{
	u32 disable, readiness;
	int ret;

	ret = readl_poll_timeout(a->engine + AES_READY, readiness,
		readiness != U32_MAX &&
		(readiness & AES_READY_MASK) == AES_READY_MASK, 25000, 5000000);
	if (ret)
		return ret;
	/* Pinned OverrideRegMap caches this SAME bank+0 word unchanged; its
	 * _isKeyDisabled(3000) selects bit3. No DT override exists on this board.
	 */
	disable = readl(a->disable);
	if (disable == U32_MAX)
		return -EIO;
	memset(capability, 0, sizeof(*capability));
	capability->abi_version = OMVM_UID1_ABI_VERSION;
	capability->dsb_available = !(disable & BIT(3));
	capability->readiness = readiness;
	return 0;
}

static int uid1_capability(struct uid1_provider *a, void __user *arg)
{
	struct omvm_uid1_capability capability;
	bool temporary_power = !a->power_held;
	int ret, put_ret;

	if (temporary_power) {
		ret = pm_runtime_resume_and_get(a->dev);
		if (ret < 0)
			return ret;
	}
	ret = uid1_sample_capability(a, &capability);
	if (temporary_power) {
		/* put decrements the reference even on failure: never double-put.
		 * No session/DMA was started, so no uncertain DMA is being released.
		 */
		put_ret = pm_runtime_put_sync_suspend(a->dev);
		if (put_ret < 0)
			return put_ret;
	}
	if (ret)
		return ret;
	return copy_to_user(arg, &capability, sizeof(capability)) ? -EFAULT : 0;
}

static int uid1_start_session(struct uid1_provider *a)
{
	u32 status, fifo, tag;
	int ret;

	if (a->engine_started)
		return 0;
	ret = uid1_alloc_dma(a);
	if (ret)
		return ret;
	if (!try_module_get(THIS_MODULE)) {
		uid1_free_dma_before_session(a);
		return -ENODEV;
	}
	WRITE_ONCE(a->pinned, true);
	/* No module_put after this point, even for a failed session. */
	ret = pm_runtime_resume_and_get(a->dev);
	if (ret < 0)
		goto poison;
	WRITE_ONCE(a->power_held, true);
	ret = uid1_check_ready(a, false);
	if (ret)
		goto poison;
	/* Conservative idle gate. Never take over queued/pending firmware work. */
	fifo = readl(a->engine + AES_FIFO_STATUS);
	tag = readl(a->engine + AES_TAG_STATUS);
	if (fifo == U32_MAX || tag == U32_MAX ||
	    ((fifo >> 8) & 0xff) || (tag & AES_READS_PENDING)) {
		ret = -EBUSY;
		goto poison;
	}
	status = readl(a->engine + AES_IRQ_STATUS);
	if (status & AES_ERROR_MASK) {
		ret = -EIO;
		goto poison;
	}
	/* Pinned revision-3 native order. No reset/DKEY access. */
	writel(status, a->engine + AES_IRQ_STATUS);
	enable_irq(a->irq);
	a->irq_enabled = true;
	writel(AES_INTERRUPT_MASK, a->engine + AES_IRQ_MASK);
	writel(0x40, a->engine + AES_WATERMARK);
	writel(1, a->engine + AES_CONTROL);
	a->engine_started = true;
	uid1_irq_disable(a);
	if (uid1_poisoned(a))
		return -EIO;
	return 0;
poison:
	uid1_poison(a, ret);
	return ret;
}

static void uid1_fifo_word(struct uid1_provider *a, u32 word)
{
	writel(word, a->engine + AES_FIFO);
}

static void uid1_fifo_bytes(struct uid1_provider *a, const u8 bytes[16])
{
	unsigned int i;

	for (i = 0; i < 16; i += 4)
		uid1_fifo_word(a, get_unaligned_le32(bytes + i));
}

static void uid1_wipe_completed_dma(struct uid1_provider *a)
{
	/* Only after matching fresh completion; never called on uncertain DMA. */
	memzero_explicit(a->src, 16);
	memzero_explicit(a->dst, 16);
	memzero_explicit(a->iv_result, 16);
}

enum uid1_hw_mode {
	UID1_HW_TEST_ENCRYPT,
	UID1_HW_PARENT_ENCRYPT,
	UID1_HW_TEST_DECRYPT,
	UID1_HW_DSB_DECRYPT,
};

static int uid1_hardware_block_mode(struct uid1_provider *a,
			 enum uid1_hw_mode mode, const u8 input[16],
			 const u8 iv[16], u8 out[16], u8 *updated_iv,
			 const u8 *dsb_context, const u8 *key_field)
{
	struct omvm_uid1_capability capability;
	unsigned long flags;
	u32 status, after, tag, fifo;
	bool uid1 = mode == UID1_HW_PARENT_ENCRYPT;
	bool dsb = mode == UID1_HW_DSB_DECRYPT;
	bool decrypt = mode == UID1_HW_TEST_DECRYPT || dsb;
	unsigned int words = dsb ? 27 : uid1 ? 14 : 18;
	int ret;

	if (mode > UID1_HW_DSB_DECRYPT ||
	    (dsb && (!dsb_context || !key_field)))
		return -EINVAL;
	/* DSB is available only after explicit KAT + real UID1 INIT. Its fresh
	 * capability check precedes ALL command writes and DMA-buffer changes.
	 */
	if (dsb) {
		if (a->state != OMVM_UID1_READY || !a->power_held ||
		    !a->engine_started)
			return -ENOKEY;
		ret = uid1_sample_capability(a, &capability);
		if (ret)
			return ret;
		if (!capability.dsb_available)
			return -ENOKEY;
	}
	ret = uid1_start_session(a);
	if (ret)
		return ret;
	ret = uid1_check_ready(a, uid1);
	if (ret)
		goto poison;
	uid1_irq_disable(a);
	status = readl(a->engine + AES_IRQ_STATUS);
	if (status & AES_ERROR_MASK) {
		ret = -EIO;
		goto poison;
	}
	writel(status, a->engine + AES_IRQ_STATUS);
	/* Read back acknowledgement before arming a fresh expected tag. */
	after = readl(a->engine + AES_IRQ_STATUS);
	tag = readl(a->engine + AES_TAG_STATUS);
	fifo = readl(a->engine + AES_FIFO_STATUS);
	if (after & (AES_ERROR_MASK | AES_COMPLETE) || tag == U32_MAX ||
	    (tag & AES_READS_PENDING) || fifo == U32_MAX ||
	    ((fifo >> 8) & 0xff) ||
	    ((fifo >> 8) & 0xff) + words > AES_FIFO_WORDS) {
		ret = -EBUSY;
		goto poison;
	}
	memcpy(a->src, input, 16);
	memset(a->dst, 0, 16);
	memset(a->iv_result, 0, 16);
	dma_wmb();
	reinit_completion(&a->done);
	spin_lock_irqsave(&a->state_lock, flags);
	a->expected_tag = (tag + 1) & 0xff;
	a->hw_status = 0;
	a->hw_tag = tag;
	a->result = -EINPROGRESS;
	a->active = true;
	spin_unlock_irqrestore(&a->state_lock, flags);

	/* Full batch capacity was checked with IRQ disabled and one sole writer.
	 * Publish pending state before marker; enable IRQ only after all writes.
	 * Engine interrupt mask remains native-enabled, so completion latches.
	 */
	if (dsb) {
		uid1_fifo_word(a, 0x30000000);
		uid1_fifo_bytes(a, dsb_context);
		uid1_fifo_bytes(a, dsb_context + 16);
	}
	uid1_fifo_word(a, dsb ? 0x10090000 : uid1 ? 0x11910000 :
			 decrypt ? 0x10010000 : 0x10110000);
	if (!uid1)
		uid1_fifo_bytes(a, dsb ? key_field : kat_key);
	uid1_fifo_word(a, 0x20000000);
	uid1_fifo_bytes(a, iv);
	wmb(); /* native OSSynchronizeIO boundary after key and IV */
	uid1_fifo_word(a, 0x50000010);
	uid1_fifo_word(a, 0); /* complete DMA ranges validated below 2^32 */
	uid1_fifo_word(a, lower_32_bits(a->src_dma));
	uid1_fifo_word(a, lower_32_bits(a->dst_dma));
	uid1_fifo_word(a, 0x80000100);
	uid1_fifo_word(a, 0x60000000);
	uid1_fifo_word(a, lower_32_bits(a->iv_dma));
	uid1_fifo_word(a, 0x88000000 | a->expected_tag);
	enable_irq(a->irq);
	a->irq_enabled = true;
	if (!wait_for_completion_timeout(&a->done,
				 msecs_to_jiffies(AES_REQUEST_TIMEOUT_MS))) {
		ret = -ETIMEDOUT;
		goto poison;
	}
	uid1_irq_disable(a); /* synchronize bounded thread before consuming DMA */
	ret = READ_ONCE(a->result);
	if (ret || uid1_poisoned(a)) {
		ret = ret ? ret : -EIO;
		goto poison;
	}
	dma_rmb();
	/* CBC's next IV is ciphertext: output for encrypt, INPUT for decrypt. */
	/* input is the immutable kernel request copy, not device-owned DMA. */
	if (crypto_memneq(decrypt ? input : a->dst, a->iv_result, 16)) {
		ret = -EIO;
		goto poison;
	}
	memcpy(out, a->dst, 16);
	if (updated_iv)
		memcpy(updated_iv, a->iv_result, 16);
	uid1_wipe_completed_dma(a);
	return 0;
poison:
	uid1_poison(a, ret);
	uid1_irq_disable(a);
	/* No abort/stop/PM put/unmap/free/wipe, even if a late IRQ completes. */
	return ret;
}

/* Preserve the original fixed-purpose encryption-only derivation boundary. */
static int uid1_hardware_block(struct uid1_provider *a, bool uid1,
			       const u8 input[16], const u8 iv[16], u8 out[16])
{
	return uid1_hardware_block_mode(a,
		uid1 ? UID1_HW_PARENT_ENCRYPT : UID1_HW_TEST_ENCRYPT,
		input, iv, out, NULL, NULL, NULL);
}

static int uid1_cbc_crypt(struct crypto_skcipher *tfm, bool decrypt,
			  u8 *data, unsigned int length, u8 iv[16])
{
	struct skcipher_request *request;
	struct scatterlist sg;
	int ret;

	if (!length || length > OMVM_UID1_MAX_PAYLOAD || length % 16)
		return -EINVAL;
	request = skcipher_request_alloc(tfm, GFP_KERNEL);
	if (!request)
		return -ENOMEM;
	skcipher_request_set_callback(request, CRYPTO_TFM_REQ_MAY_SLEEP, NULL, NULL);
	sg_init_one(&sg, data, length);
	skcipher_request_set_crypt(request, &sg, &sg, length, iv);
	ret = decrypt ? crypto_skcipher_decrypt(request) :
			crypto_skcipher_encrypt(request);
	skcipher_request_free(request);
	return ret;
}

static int uid1_software_kat(struct uid1_provider *a)
{
	u8 *data, *iv;
	unsigned int i;
	int ret;

	/* sg_init_one requires directly mapped memory, not a VMAP_STACK buffer. */
	data = kzalloc(32, GFP_KERNEL);
	if (!data)
		return -ENOMEM;
	iv = data + 16;
	/* Temporary public KAT keys never authorize a payload operation: state
	 * remains UNTESTED/SELFTEST_PASSED until INIT replaces BOTH contexts with
	 * real UID1-derived keys. No derivation fallback exists.
	 */
	for (i = 0; i < 2; i++) {
		ret = crypto_skcipher_setkey(a->cbc[i], kat_key, sizeof(kat_key));
		if (ret)
			goto out;
	}
	memcpy(data, kat_plain, 16);
	memcpy(iv, kat_iv, 16);
	ret = uid1_cbc_crypt(a->cbc[0], false, data, 16, iv);
	if (ret)
		goto out;
	if (crypto_memneq(data, kat_cipher, 16) ||
	    crypto_memneq(iv, kat_cipher, 16)) {
		ret = -EBADMSG;
		goto out;
	}
	memcpy(data, kat_cipher, 16);
	memcpy(iv, kat_iv, 16);
	ret = uid1_cbc_crypt(a->cbc[1], true, data, 16, iv);
	if (!ret && (crypto_memneq(data, kat_plain, 16) ||
		     crypto_memneq(iv, kat_cipher, 16)))
		ret = -EBADMSG;
out:
	kfree_sensitive(data);
	return ret;
}

static int uid1_selftest(struct uid1_provider *a)
{
	u8 result[16];
	int ret;

	if (a->state != OMVM_UID1_UNTESTED)
		return -EALREADY;
	ret = uid1_hardware_block(a, false, kat_plain, kat_iv, result);
	if (!ret && crypto_memneq(result, kat_cipher, 16)) {
		ret = -EBADMSG;
		uid1_poison(a, ret);
	}
	memzero_explicit(result, sizeof(result));
	if (!ret) {
		/* Public NIST vector tests actual hardware CBC-decrypt direction and
		 * returned IV before accepting ANY opaque format2 input. No DSB or
		 * fabricated opaque key is involved in this known-answer test.
		 */
		ret = uid1_hardware_block_mode(a, UID1_HW_TEST_DECRYPT,
			kat_cipher, kat_iv, result, NULL, NULL, NULL);
		if (!ret && crypto_memneq(result, kat_plain, 16)) {
			ret = -EBADMSG;
			uid1_poison(a, ret);
		}
		memzero_explicit(result, sizeof(result));
	}
	if (!ret) {
		ret = uid1_software_kat(a);
		if (ret)
			uid1_poison(a, ret);
	}
	if (!ret)
		WRITE_ONCE(a->state, OMVM_UID1_SELFTEST_PASSED);
	return ret;
}

static int uid1_initialize(struct uid1_provider *a, void __user *arg)
{
	struct omvm_uid1_init request;
	u8 digest[32], derived[16], iv[16] = {};
	SHASH_DESC_ON_STACK(desc, a->sha);
	unsigned int i;
	int ret = -EINVAL;

	memset(&request, 0, sizeof(request));
	if (a->state != OMVM_UID1_SELFTEST_PASSED)
		return -EPERM;
	if (copy_from_user(&request, arg, sizeof(request))) {
		ret = -EFAULT;
		goto out;
	}
	if (request.abi_version != OMVM_UID1_ABI_VERSION || request.reserved)
		goto out;
	desc->tfm = a->sha;
	ret = crypto_shash_digest(desc, request.seed_bundle, 32, digest);
	if (ret)
		goto out;
	if (crypto_memneq(digest, bundle_digest, 32)) {
		ret = -EKEYREJECTED;
		goto out;
	}
	for (i = 0; i < 2; i++) {
		ret = uid1_hardware_block(a, true, request.seed_bundle + i * 16,
					  iv, derived);
		if (ret)
			goto out;
		ret = crypto_skcipher_setkey(a->cbc[i], derived, 16);
		memzero_explicit(derived, sizeof(derived));
		if (ret) {
			uid1_poison(a, ret);
			goto out;
		}
	}
	WRITE_ONCE(a->state, OMVM_UID1_READY);
out:
	shash_desc_zero(desc);
	memzero_explicit(digest, sizeof(digest));
	memzero_explicit(derived, sizeof(derived));
	memzero_explicit(&request, sizeof(request));
	return ret;
}

static int uid1_transform(struct uid1_provider *a, void __user *arg)
{
	struct omvm_uid1_transform *request;
	u8 iv[16] = {};
	unsigned int index;
	int ret = -EINVAL;

	if (a->state != OMVM_UID1_READY)
		return -ENOKEY;
	request = memdup_user(arg, sizeof(*request));
	if (IS_ERR(request))
		return PTR_ERR(request);
	if (request->abi_version != OMVM_UID1_ABI_VERSION ||
	    (request->operation != OMVM_UID1_OPERATION_ENCRYPT &&
	     request->operation != OMVM_UID1_OPERATION_DECRYPT) ||
	    request->reserved || request->iv_present > 1 ||
	    !request->length || request->length > OMVM_UID1_MAX_PAYLOAD ||
	    request->length % 16 ||
	    memchr_inv(request->data + request->length, 0,
		       OMVM_UID1_MAX_PAYLOAD - request->length) ||
	    (!request->iv_present && memchr_inv(request->iv, 0, 16)))
		goto out;
	if (request->purpose == OMVM_UID1_PURPOSE_899)
		index = 0;
	else if (request->purpose == OMVM_UID1_PURPOSE_89C)
		index = 1;
	else
		goto out;
	if (request->iv_present)
		memcpy(iv, request->iv, 16);
	ret = uid1_cbc_crypt(a->cbc[index],
		request->operation == OMVM_UID1_OPERATION_DECRYPT,
		request->data, request->length, iv);
	if (ret)
		goto out;
	if (uid1_poisoned(a)) {
		ret = -EIO;
		goto out;
	}
	if (request->iv_present)
		memcpy(request->iv, iv, 16);
	if (copy_to_user(arg, request, sizeof(*request)))
		ret = -EFAULT;
out:
	memzero_explicit(iv, sizeof(iv));
	kfree_sensitive(request);
	return ret;
}

static int uid1_dsb_decrypt(struct uid1_provider *a, void __user *arg)
{
	struct omvm_uid1_dsb_decrypt *request;
	int ret = -EINVAL;

	if (a->state != OMVM_UID1_READY)
		return -ENOKEY;
	request = memdup_user(arg, sizeof(*request));
	if (IS_ERR(request))
		return PTR_ERR(request);
	if (request->abi_version != OMVM_UID1_ABI_VERSION || request->reserved)
		goto out;
	ret = uid1_hardware_block_mode(a, UID1_HW_DSB_DECRYPT,
		request->data, request->iv, request->data, request->iv,
		request->dsb_context, request->key_field);
	if (ret)
		goto out;
	/* Only completed payload/IV; never copy opaque key/context inputs back.
	 * The one copy can partially fault; callers must never retry on EFAULT.
	 */
	if (copy_to_user((u8 __user *)arg +
			offsetof(struct omvm_uid1_dsb_decrypt, iv),
			request->iv, 32))
		ret = -EFAULT;
out:
	kfree_sensitive(request);
	return ret;
}

static int uid1_pm_event(struct notifier_block *nb, unsigned long event, void *unused)
{
	struct uid1_provider *a = container_of(nb, struct uid1_provider, pm_notifier);
	unsigned long flags;
	int ret = NOTIFY_OK;

	(void)unused;
	spin_lock_irqsave(&a->state_lock, flags);
	switch (event) {
	case PM_SUSPEND_PREPARE:
	case PM_HIBERNATION_PREPARE:
	case PM_RESTORE_PREPARE:
		if (a->busy || a->pinned || a->power_held ||
		    a->state == OMVM_UID1_POISONED)
			ret = notifier_from_errno(-EBUSY);
		else
			a->pm_transition = true;
		break;
	case PM_POST_SUSPEND:
	case PM_POST_HIBERNATION:
	case PM_POST_RESTORE:
		a->pm_transition = false;
		break;
	}
	spin_unlock_irqrestore(&a->state_lock, flags);
	return ret;
}

static long uid1_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct uid1_provider *a = container_of(file->private_data,
						struct uid1_provider, misc);
	struct omvm_uid1_status status = {};
	void __user *user = (void __user *)arg;
	unsigned long flags;
	int ret;

	if (!uid1_admin())
		return -EPERM;
	if (cmd == OMVM_UID1_IOC_STATUS) {
		spin_lock_irqsave(&a->state_lock, flags);
		status.abi_version = OMVM_UID1_ABI_VERSION;
		status.state = a->state;
		status.last_errno = a->last_errno;
		status.hw_status = a->hw_status;
		status.hw_tag = a->hw_tag;
		status.completed_ops = a->completed_ops;
		status.flags = (a->busy ? OMVM_UID1_STATUS_BUSY : 0) |
			(a->pinned ? OMVM_UID1_STATUS_PINNED : 0) |
			(a->power_held ? OMVM_UID1_STATUS_POWER_HELD : 0);
		spin_unlock_irqrestore(&a->state_lock, flags);
		return copy_to_user(user, &status, sizeof(status)) ? -EFAULT : 0;
	}
	if (cmd != OMVM_UID1_IOC_SELFTEST && cmd != OMVM_UID1_IOC_INIT &&
	    cmd != OMVM_UID1_IOC_TRANSFORM && cmd != OMVM_UID1_IOC_CAPABILITY &&
	    cmd != OMVM_UID1_IOC_DSB_DECRYPT)
		return -ENOTTY;
	if (cmd == OMVM_UID1_IOC_SELFTEST && arg)
		return -EINVAL;
	if (!mutex_trylock(&a->op_lock))
		return -EBUSY;
	spin_lock_irqsave(&a->state_lock, flags);
	if (a->pm_transition || a->state == OMVM_UID1_POISONED) {
		ret = a->pm_transition ? -EBUSY : -EIO;
		spin_unlock_irqrestore(&a->state_lock, flags);
		goto unlock;
	}
	a->busy = true;
	spin_unlock_irqrestore(&a->state_lock, flags);
	if (cmd == OMVM_UID1_IOC_SELFTEST)
		ret = uid1_selftest(a);
	else if (cmd == OMVM_UID1_IOC_INIT)
		ret = uid1_initialize(a, user);
	else if (cmd == OMVM_UID1_IOC_CAPABILITY)
		ret = uid1_capability(a, user);
	else if (cmd == OMVM_UID1_IOC_DSB_DECRYPT)
		ret = uid1_dsb_decrypt(a, user);
	else
		ret = uid1_transform(a, user);
	spin_lock_irqsave(&a->state_lock, flags);
	a->busy = false;
	if (a->state != OMVM_UID1_POISONED)
		a->last_errno = ret;
	spin_unlock_irqrestore(&a->state_lock, flags);
unlock:
	mutex_unlock(&a->op_lock);
	return ret;
}

static int uid1_open(struct inode *inode, struct file *file)
{
	return uid1_admin() ? nonseekable_open(inode, file) : -EPERM;
}

static const struct file_operations uid1_fops = {
	.owner = THIS_MODULE,
	.open = uid1_open,
	.unlocked_ioctl = uid1_ioctl,
#ifdef CONFIG_COMPAT
	.compat_ioctl = compat_ptr_ioctl,
#endif
};

static void __iomem *uid1_map(struct platform_device *pdev, unsigned int index,
			    const char *name, resource_size_t start,
			    resource_size_t size)
{
	struct resource *r = platform_get_resource(pdev, IORESOURCE_MEM, index);

	if (!r || r != platform_get_resource_byname(pdev, IORESOURCE_MEM, name) ||
	    r->start != start || resource_size(r) != size)
		return IOMEM_ERR_PTR(-EINVAL);
	return devm_ioremap_resource(&pdev->dev, r);
}

static int uid1_get_irq(struct platform_device *pdev)
{
	struct device_node *np;
	struct irq_domain *domain;
	struct irq_data *irqdata;
	struct resource resource;
	struct irq_fwspec spec = { .param_count = 4,
		.param = { 0 /* AIC_IRQ */, 0, 1117, IRQ_TYPE_LEVEL_HIGH } };
	u32 cells;
	unsigned int irq;
	int ret;

	/* A malformed/deferred declared IRQ must never select the fallback. */
	if (of_property_present(pdev->dev.of_node, "interrupts") ||
	    of_property_present(pdev->dev.of_node, "interrupts-extended") ||
	    !j314c_irq_diagnostic)
		return platform_get_irq(pdev, 0);
	np = of_find_node_by_path("/soc/interrupt-controller@28e100000");
	if (!np)
		return -ENODEV;
	ret = -EINVAL;
	if (!of_device_is_available(np) ||
	    !of_device_is_compatible(np, "apple,t6000-aic") ||
	    !of_device_is_compatible(np, "apple,aic2") ||
	    of_property_read_u32(np, "#interrupt-cells", &cells) || cells != 4 ||
	    of_address_to_resource(np, 0, &resource) ||
	    resource.start != 0x28e100000ULL || resource_size(&resource) != 0xc000 ||
	    of_address_to_resource(np, 1, &resource) ||
	    resource.start != 0x28e10c000ULL || resource_size(&resource) != 4)
		goto out;
	spec.fwnode = of_fwnode_handle(np);
	domain = irq_find_matching_fwspec(&spec, DOMAIN_BUS_WIRED);
	if (!domain) {
		ret = -EPROBE_DEFER;
		goto out;
	}
	/* Pinned AIC2 encoding: IRQ type 1<<16 | die0 | hardware number1117.
	 * The precheck/create pair is not atomic. No competing IRQ owner is
	 * allowed in this controlled workflow; exclusive request follows.
	 */
	if (irq_find_mapping(domain, 0x1045d)) {
		ret = -EBUSY;
		goto out;
	}
	irq = irq_create_fwspec_mapping(&spec);
	if (!irq) {
		ret = -ENXIO;
		goto out;
	}
	/* Never dispose this mapping, including later probe failure: the API
	 * may have reused a concurrent idle mapping and has no ownership bit.
	 */
	irqdata = irq_get_irq_data(irq);
	if (!irqdata || irqdata->domain != domain || irqdata->hwirq != 0x1045d ||
	    irq_get_trigger_type(irq) != IRQ_TYPE_LEVEL_HIGH) {
		ret = -EINVAL;
		goto out;
	}
	dev_info(&pdev->dev, "explicit diagnostic AIC2 mapping retained until reset\n");
	ret = irq;
out:
	of_node_put(np);
	return ret;
}

static int uid1_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct uid1_provider *a;
	unsigned int i;
	int ret;

	static_assert(sizeof(struct omvm_uid1_init) == 40);
	static_assert(sizeof(struct omvm_uid1_transform) == 4136);
	static_assert(sizeof(struct omvm_uid1_status) == 64);
	static_assert(sizeof(struct omvm_uid1_capability) == 64);
	static_assert(sizeof(struct omvm_uid1_dsb_decrypt) == 88);
	static_assert(offsetof(struct omvm_uid1_dsb_decrypt, iv) == 56);
	static_assert(offsetof(struct omvm_uid1_dsb_decrypt, data) == 72);
	if (!of_machine_is_compatible("apple,j314c") ||
	    !of_machine_is_compatible("apple,t6001"))
		return -ENODEV;
	if (!dev->pm_domain ||
	    of_count_phandle_with_args(dev->of_node, "power-domains",
				      "#power-domain-cells") != 1 ||
	    of_count_phandle_with_args(dev->of_node, "iommus", "#iommu-cells") != 2 ||
	    !iommu_get_domain_for_dev(dev) ||
	    platform_get_resource(pdev, IORESOURCE_MEM, 2))
		return -EINVAL;
	a = kzalloc(sizeof(*a), GFP_KERNEL);
	if (!a)
		return -ENOMEM;
	a->dev = dev;
	mutex_init(&a->op_lock);
	spin_lock_init(&a->state_lock);
	init_completion(&a->done);
	a->engine = uid1_map(pdev, 0, "engine", 0x39b060000ULL, 0x4000);
	if (IS_ERR(a->engine)) {
		ret = PTR_ERR(a->engine);
		goto free;
	}
	a->disable = uid1_map(pdev, 1, "key-disable", 0x2922d0000ULL, 0x8000);
	if (IS_ERR(a->disable)) {
		ret = PTR_ERR(a->disable);
		goto free;
	}
	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(32));
	if (ret)
		goto free;
	a->sha = crypto_alloc_shash("sha256", 0, 0);
	if (IS_ERR(a->sha)) {
		ret = PTR_ERR(a->sha);
		a->sha = NULL;
		goto free;
	}
	for (i = 0; i < 2; i++) {
		/* Exclude asynchronous algorithms: this bounded payload path is sync. */
		a->cbc[i] = crypto_alloc_skcipher("cbc(aes)", 0, CRYPTO_ALG_ASYNC);
		if (IS_ERR(a->cbc[i])) {
			ret = PTR_ERR(a->cbc[i]);
			a->cbc[i] = NULL;
			goto crypto_free;
		}
	}
	/* Allocate software prerequisites before consuming a diagnostic mapping. */
	a->irq = uid1_get_irq(pdev);
	if (a->irq < 0) {
		ret = a->irq;
		goto crypto_free;
	}
	ret = request_threaded_irq(a->irq, NULL, uid1_irq_thread,
				  IRQF_ONESHOT | IRQF_NO_AUTOEN,
				  "omvm-uid1-provider", a);
	if (ret)
		goto crypto_free;
	a->pm_notifier.notifier_call = uid1_pm_event;
	ret = register_pm_notifier(&a->pm_notifier);
	if (ret)
		goto irq_free;
	ret = devm_pm_runtime_enable(dev);
	if (ret)
		goto notifier_free;
	a->misc.minor = MISC_DYNAMIC_MINOR;
	a->misc.name = "omvm-uid1-provider";
	a->misc.fops = &uid1_fops;
	a->misc.mode = 0600;
	a->misc.parent = dev;
	ret = misc_register(&a->misc);
	if (ret)
		goto notifier_free;
	platform_set_drvdata(pdev, a);
	return 0;
notifier_free:
	unregister_pm_notifier(&a->pm_notifier);
irq_free:
	free_irq(a->irq, a);
crypto_free:
	for (i = 0; i < 2; i++)
		if (a->cbc[i])
			crypto_free_skcipher(a->cbc[i]);
	if (a->sha)
		crypto_free_shash(a->sha);
free:
	kfree(a);
	return ret;
}

static void uid1_remove(struct platform_device *pdev)
{
	struct uid1_provider *a = platform_get_drvdata(pdev);
	unsigned int i;

	/* Pinned module + suppressed bind attrs exclude ordinary session removal.
	 * A supplier/DT teardown cannot be vetoed here; it is expressly excluded.
	 */
	if (WARN_ON(a->pinned))
		return;
	misc_deregister(&a->misc);
	unregister_pm_notifier(&a->pm_notifier);
	free_irq(a->irq, a);
	uid1_free_dma_before_session(a);
	for (i = 0; i < 2; i++)
		crypto_free_skcipher(a->cbc[i]);
	crypto_free_shash(a->sha);
	kfree_sensitive(a);
}

static const struct of_device_id uid1_match[] = {
	{ .compatible = "apple,t6000-aes" },
	{ }
};
/* Deliberately no MODULE_DEVICE_TABLE alias: loading/claim is manual only. */
static struct platform_driver uid1_driver = {
	.probe = uid1_probe,
	.remove = uid1_remove,
	.driver = {
		.name = "omvm-uid1-provider",
		.of_match_table = uid1_match,
		.suppress_bind_attrs = true,
	},
};
module_platform_driver(uid1_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Experimental fixed-purpose T6001 UID1 provider; explicit actions only");
