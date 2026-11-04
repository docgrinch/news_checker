import unittest

import app


class T(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(app.clean("<p>a &amp;\n b</p>"), "a & b")
        self.assertEqual(app.clean("one two three", 8), "one two…")

    def test_safe_link(self):
        self.assertEqual(app.safe_link("https://x.com/a"), "https://x.com/a")
        self.assertIsNone(app.safe_link("javascript:alert(1)"))
        self.assertIsNone(app.safe_link(None))

    def test_render_escapes_feed_content(self):
        app.state.update(items=[{"source": "S", "title": "<script>x</script>", "link": "https://x.com/?a=1&b=2",
                                 "text": "body", "ts": 0}], updated="now")
        page = app.render()
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("a=1&amp;b=2", page)

    def test_filters(self):
        now = app.time.time()
        app.state.update(items=[{"source": "Numerama", "title": "new", "link": "https://a", "text": "", "ts": now},
                                {"source": "SecurityWeek", "title": "old", "link": "https://b", "text": "", "ts": now - 5 * 86400}],
                         updated="now")
        self.assertIn("2 articles", app.render())
        self.assertIn("1 articles", app.render("source=Numerama"))
        self.assertIn("<h2>new</h2>", app.render("days=3"))
        self.assertNotIn("<h2>old</h2>", app.render("days=3"))
        self.assertIn("1 articles", app.render("source=Numerama&source=SecurityWeek&days=1"))
        self.assertIn("2 articles", app.render("source=<bogus>&days=evil"))  # unknown values are ignored

    def test_feed_image(self):
        e = {"links": [{"rel": "enclosure", "type": "image/jpeg", "href": "https://x/a.jpg"}]}
        self.assertEqual(app.feed_image(e, ""), "https://x/a.jpg")
        self.assertEqual(app.feed_image({}, '<p><img alt="" src="https://x/b.png?a=1&amp;b=2"></p>'), "https://x/b.png?a=1&b=2")
        self.assertIsNone(app.feed_image({}, '<img src="javascript:x">'))


if __name__ == "__main__":
    unittest.main()
