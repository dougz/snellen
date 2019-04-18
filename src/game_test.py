import unittest

import game

class PuzzleTest(unittest.TestCase):
  def test_canonical(self):
    def check(before, after):
      self.assertEqual(game.Puzzle.canonicalize_answer(before), after)

    check("foo", "FOO")

    check("123", "")

    check("car 54", "CAR")

    check("Al Kaline stuck in Ph one booth",
          "ALKALINESTUCKINPHONEBOOTH")

    check("Montréal, über, 12.89, Mère, Françoise, noël, 889",
          "MONTREALUBERMEREFRANCOISENOEL")

    check("✈✈✈ Galactic Trendsetters ✈✈✈",
          "✈✈✈GALACTICTRENDSETTERS✈✈✈")

    check("👠", "👠")

  def test_respace(self):
    def check(before, after):
      self.assertEqual(game.Puzzle.respace_text(before), after)

    check("Foo.", "Foo.")
    check(" Hello, world! ", "Hello, world!")
    check("Multi-line\nresponse.", "Multi-line response.")


if __name__ == "__main__":
  unittest.main()


