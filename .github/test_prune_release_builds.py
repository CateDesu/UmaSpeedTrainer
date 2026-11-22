import unittest

from prune_release_builds import BINARIES, REQUIRED, obsolete_builds


def release(tag, **options):
    assets = [dict(id=i, name=name, state="uploaded", size=10)
              for i, name in enumerate(sorted(REQUIRED | {"notes.pdf"}), 1)]
    return dict(tag_name=tag, assets=assets, draft=False, prerelease=False) | options


class RetentionTests(unittest.TestCase):
    def test_only_older_stable_binary_assets_are_selected(self):
        latest = release("v0.10.0")
        history = [latest, release("v0.9.0"), release("v0.11.0"), release("v0.8.0", draft=True),
                   release("v0.7.0", prerelease=True), release("nightly")]
        selected = [(tag, a["name"]) for tag, a in obsolete_builds("v0.10.0", latest, history)]
        self.assertCountEqual(selected, [("v0.9.0", name) for name in BINARIES])

    def test_incomplete_upload_stops_cleanup(self):
        latest = release("v2.0.0")
        next(a for a in latest["assets"] if a["name"] in BINARIES)["size"] = 0
        with self.assertRaises(ValueError):
            list(obsolete_builds("v2.0.0", latest, [release("v1.0.0")]))

    def test_retry_of_old_release_leaves_assets_alone(self):
        self.assertEqual(list(obsolete_builds("v1.0.0", release("v2.0.0"), [release("v0.2.0")])), [])


if __name__ == "__main__":
    unittest.main()
