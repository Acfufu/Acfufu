"""Check the generated pet timeline, including state and loop boundaries."""
import bisect
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gen_acfufu_card as card


class PetMotionTests(unittest.TestCase):
    def test_timeline_and_rendered_frames_are_exclusive(self):
        ns = {'s': 'http://www.w3.org/2000/svg'}
        for slot in ('morning', 'day', 'evening', 'night'):
            for tier in card.TIERS:
                with self.subTest(slot=slot, tier=tier):
                    timeline = card.pet_timeline(slot, tier)
                    root = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">'
                                         + card.pet_scene(20, 50, slot, tier) + '</svg>')
                    dynamic = root.find('.//s:g[@class="pet-animated"]', ns)
                    animations = [(image, image.find('s:animate', ns)) for image in dynamic]
                    total = sum(item[2] for item in timeline)
                    self.assertTrue(all(a.get('dur') == f'{total}ms' for _, a in animations))
                    elapsed = 0
                    for state, frame, duration in timeline:
                        # Evaluate away from rounded keyTimes and across two loops.
                        for cycle in (0, 1):
                            phase = ((elapsed + duration / 2 + cycle * total) % total) / total
                            visible = []
                            for image, anim in animations:
                                times = [float(x) for x in anim.get('keyTimes').split(';')]
                                values = anim.get('values').split(';')
                                if int(values[bisect.bisect_right(times, phase) - 1]):
                                    visible.append(image.get('href').split(',', 1)[1])
                            self.assertEqual(visible, [card.STATES[state][1][frame]],
                                             (state, frame, elapsed))
                        elapsed += duration
                    static = root.find('.//s:image[@class="pet-static"]', ns)
                    self.assertIsNotNone(static)
                    card.C = card.DARK
                    css = card.build_css()
                    self.assertIn('.pet-animated { display:none; }', css)
                    self.assertIn('.pet-static { display:inline; }', css)

    def test_every_beat_starts_at_first_frame(self):
        for slot, tiers in card.BEAT.items():
            for tier, sheet in tiers.items():
                timeline = card.pet_timeline(slot, tier)
                index = 0
                for state, loops in sheet:
                    self.assertEqual(timeline[index][:2], (state, 0))
                    index += len(card.STATES[state][0]) * loops
                self.assertEqual(index, len(timeline))

    def test_freeze_shifts_all_frames_to_same_clock(self):
        root = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">'
                             + card.pet_scene(0, 0, 'day', 'calm', ('waving', 2)) + '</svg>')
        animations = root.findall('.//{http://www.w3.org/2000/svg}animate')
        begins = {a.get('begin') for a in animations}
        self.assertEqual(len(begins), 1)
        self.assertNotIn(None, begins)
        with self.assertRaises(ValueError):
            card.pet_scene(0, 0, 'night', 'calm', ('waving', 0))


if __name__ == '__main__':
    unittest.main()
