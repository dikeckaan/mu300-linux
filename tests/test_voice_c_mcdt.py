"""The voice capture tap's MCDT full watermark and DMA fragment are module parameters on 5.4 (FINDINGS 24d, 193).

* audio-fe-voice-c-mcdt-params.patch changes only sprd-fe-dai.c: voice_c_wmk and voice_c_frag, in words, default to
  the vendor's MCDT_FULL_WMK_VOICE_CAPTURE and MCDT_VOICE_C_FRAGMENT, and a value of 0 or above 511 falls back to them;
* the 5.4 audio build applies it (its marker is a line the patch adds)."""
import re
import unittest

from helpers import TOP

PATCH54 = TOP / 'kernel' / 'patches' / 'audio-fe-voice-c-mcdt-params.patch'
BUILD_AUDIO = TOP / 'kernel' / 'build-audio.sh'


def added(patch):
    return '\n'.join(l[1:] for l in patch.splitlines() if l.startswith('+') and not l.startswith('+++'))


class VoiceCaptureMCDT(unittest.TestCase):
    def setUp(self):
        self.patch = PATCH54.read_text()
        self.added = added(self.patch)

    def test_one_file(self):
        self.assertEqual(re.findall(r'(?m)^\+\+\+ b/(\S+)', self.patch), ['sprd/dai/vbc/v4/fe_dai/sprd-fe-dai.c'])

    def test_parameters_and_defaults(self):
        self.assertIn('static unsigned int voice_c_wmk = MCDT_FULL_WMK_VOICE_CAPTURE;', self.added)
        self.assertIn('static unsigned int voice_c_frag = MCDT_VOICE_C_FRAGMENT;', self.added)
        self.assertIn('module_param(voice_c_wmk, uint, 0644);', self.added)
        self.assertIn('module_param(voice_c_frag, uint, 0644);', self.added)
        self.assertIn('if (!voice_c_wmk || voice_c_wmk > 511)', self.added)
        self.assertIn('if (!voice_c_frag || voice_c_frag > 511)', self.added)
        # the fragment is set before the channel is enabled with the watermark
        self.assertLess(self.added.index('desc.fragmens_len = voice_c_frag;'),
                        self.added.index('mcdt_adc_dma_enable(MCDT_CHAN_VOICE_CAPTURE, voice_c_wmk);'))

    def test_built(self):
        self.assertIn('audio-fe-voice-c-mcdt-params:voice_c_wmk:sprd/dai/vbc/v4/fe_dai', BUILD_AUDIO.read_text())
        self.assertIn('voice_c_wmk', self.added)
        self.assertNotRegex(self.patch, r'\bSIP\b|[Gg]ateway')


if __name__ == '__main__':
    unittest.main()
