"""The SIPA sender and receiver threads (upstream/modules/sprd_modem/sipa_v3/sipa_skb_send.c, sipa_skb_recv.c), their
real bodies run with host pthread wait queues (no MMIO): before the IPA's first resume they touch nothing, whatever
wakes them; after it they do the vendor's work; a stop ends them while they wait, also in the main loop, where the
vendor's wait did not look at it (kthread_stop() then waited for ever). The threads are stopped by devm before their
memory goes, and that memory is never kfree()d. After kanoqwq's fe52afe3 (his test_sipa_worker_lifecycle.py), on this
tree's fill_started/free_started."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import TOP

SIPA = TOP / 'upstream/modules/sprd_modem/sipa_v3'


def function(source, signature):
    start = source.index(signature)
    pos = source.index('{', start)
    depth, end = 1, pos + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <unistd.h>
struct queue { pthread_mutex_t mutex; pthread_cond_t cond; };
struct sipa_skb_sender { bool free_started; struct queue free_waitq; bool free_notify_net; };
struct sipa_skb_receiver { bool fill_started; struct queue fill_recv_waitq; };
static struct queue *q;
static atomic_bool stopping, pending, interrupt_wait;
static atomic_int mmio_reads, work, waits;
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_ACQUIRE)
#define WRITE_ONCE(x, v) __atomic_store_n(&(x), (v), __ATOMIC_RELEASE)
#define current 0
#define sched_setscheduler(a, b, c) ((void)(c))
#define kthread_should_stop() atomic_load(&stopping)
#define wait_event_interruptible(queue, condition) ({ \
    int rc = 0; pthread_mutex_lock(&(queue).mutex); \
    while (!(condition)) { atomic_fetch_add(&waits, 1); \
        pthread_cond_wait(&(queue).cond, &(queue).mutex); \
        if (atomic_exchange(&interrupt_wait, false)) { rc = -1; break; } \
    } pthread_mutex_unlock(&(queue).mutex); rc; })
static bool sipa_sender_ck_unfree(struct sipa_skb_sender *s) {
    (void)s; atomic_fetch_add(&mmio_reads, 1); return !atomic_load(&pending);
}
static bool sipa_check_need_fill_cnt(void) {
    atomic_fetch_add(&mmio_reads, 1); return atomic_load(&pending);
}
static void sipa_free_sent_items(void) {
    atomic_store(&pending, false); atomic_fetch_add(&work, 1);
}
static int sipa_fill_all_free_fifo(void) { sipa_free_sent_items(); return 0; }
#define usleep_range(a, b) usleep(a)
'''

MAIN = r'''
static int (*worker)(void *);
static void *entry(void *arg) { worker(arg); return NULL; }
static void wake(void) {
    pthread_mutex_lock(&q->mutex); pthread_cond_broadcast(&q->cond); pthread_mutex_unlock(&q->mutex);
}
static void settle(void) { usleep(30000); }
static void run_case(bool receive, bool resume) {
    struct sipa_skb_sender s = { 0 };
    struct sipa_skb_receiver r = { 0 };
    pthread_t thread;
    q = receive ? &r.fill_recv_waitq : &s.free_waitq;
    pthread_mutex_init(&q->mutex, NULL); pthread_cond_init(&q->cond, NULL);
    atomic_store(&stopping, false); atomic_store(&pending, true);
    atomic_store(&interrupt_wait, false); atomic_store(&mmio_reads, 0);
    atomic_store(&work, 0); atomic_store(&waits, 0);
    worker = receive ? sipa_fill_recv_thread : sipa_free_thread;
    assert(!pthread_create(&thread, NULL, entry, receive ? (void *)&r : (void *)&s));
    settle(); assert(atomic_load(&waits) > 0);
    wake(); settle();
    atomic_store(&interrupt_wait, true); wake(); settle();
    /* queued work, a spurious wake-up and a signal: no MMIO before the first resume */
    assert(atomic_load(&mmio_reads) == 0 && atomic_load(&work) == 0);
    if (resume) {
        if (receive) WRITE_ONCE(r.fill_started, true);
        else WRITE_ONCE(s.free_started, true);
        wake(); settle(); assert(atomic_load(&work) == 1);
        assert(atomic_load(&mmio_reads) > 0);
        wake(); settle(); assert(atomic_load(&work) == 1);
        atomic_store(&pending, true); wake(); settle();
        assert(atomic_load(&work) == 2);
        /* idle in the main loop's wait, as after a resume with nothing to do */
        settle();
    }
    int before = atomic_load(&work);
    atomic_store(&stopping, true); wake();
    assert(!pthread_join(thread, NULL)); assert(atomic_load(&work) == before);
    pthread_cond_destroy(&q->cond); pthread_mutex_destroy(&q->mutex);
}
int main(void) {
    alarm(5);   /* a stop the thread does not see: the test fails instead of hanging */
    run_case(false, false); run_case(true, false);
    run_case(false, true); run_case(true, true);
    return 0;
}
'''


class Workers(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'), 'needs a C compiler')
    def test_nothing_before_the_first_resume_work_after_it_and_a_stop_ends_the_wait(self):
        send = (SIPA / 'sipa_skb_send.c').read_text()
        recv = (SIPA / 'sipa_skb_recv.c').read_text()
        code = (HARNESS + function(send, 'static int sipa_free_thread(') + '\n'
                + function(recv, 'static int sipa_fill_recv_thread(') + '\n' + MAIN)
        with tempfile.TemporaryDirectory(prefix='sipa-workers-') as tmp:
            src, exe = Path(tmp) / 'test.c', Path(tmp) / 'test'
            src.write_text(code)
            r = subprocess.run(['cc', '-std=gnu11', '-pthread', '-O2', str(src), '-o', str(exe)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_threads_are_stopped_by_devm_and_devm_memory_is_not_kfreed(self):
        for name, make in (('sipa_skb_send.c', 'int sipa_create_skb_sender('),
                           ('sipa_skb_recv.c', 'int sipa_create_skb_receiver(')):
            source = (SIPA / name).read_text()
            create = function(source, make)
            self.assertIn('devm_add_action_or_reset(ipa->dev, sipa_stop_', create)
            self.assertIn('kthread_stop(data);', source)
            self.assertIsNone(re.search(r'^\s*kfree\(', create, re.M))
        recv = function((SIPA / 'sipa_skb_recv.c').read_text(), 'int sipa_create_skb_receiver(')
        self.assertIn('ret = sipa_init_recv_array(', recv)
        destroy = function((SIPA / 'sipa_skb_send.c').read_text(), 'void destroy_sipa_skb_sender(')
        self.assertIn('devm_release_action(', destroy)
        self.assertIsNone(re.search(r'^\s*kfree\(', destroy, re.M))


if __name__ == '__main__':
    unittest.main()
