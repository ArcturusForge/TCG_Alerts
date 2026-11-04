import unittest
from tcg_alerts.deck_rules import check


def e(name, section, q): return dict(name=name, section=section, quantity=q)


class RuleTests(unittest.TestCase):
    def legal(self):
        return ([e('Jinx', 'Champion', 1), e('Jinx Legend', 'Legend', 1), e('Fury Rune', 'Runes', 12)]
                + [e(f'Card {i}', 'Main', 3) for i in range(13)]
                + [e(f'Field {i}', 'Battlefields', 1) for i in range(3)])

    def test_legal(self):
        self.assertEqual(check('Riftbound', self.legal()), [('ok', 'Deck meets Riftbound construction rules.')])

    def test_errors(self):
        deck = self.legal() + [e('Card 0', 'Sideboard', 1)] + [e('Extra', 'Sideboard', 10)]
        msgs = ' '.join(m for _, m in check('Riftbound', deck))
        self.assertIn('Card 0: 4 copies', msgs)
        self.assertIn('Sideboard has 11', msgs)

    def test_other_games_unchecked(self):
        self.assertEqual(check('Pokémon', []), [])


if __name__ == '__main__':
    unittest.main()
