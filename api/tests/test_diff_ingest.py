from app.graph.diff_ingest import parse_diff

DIFF = """diff --git a/src/billing/FeatureGate.tsx b/src/billing/FeatureGate.tsx
new file mode 100644
--- /dev/null
+++ b/src/billing/FeatureGate.tsx
@@ -0,0 +1,2 @@
+export const Gate = () => null;
+// gate
diff --git a/src/todo/model.ts b/src/todo/model.ts
--- a/src/todo/model.ts
+++ b/src/todo/model.ts
@@ -1,1 +1,2 @@
-old
+new
+added
"""


def test_parse_diff_returns_sorted_touched_files():
    files = parse_diff(DIFF)
    assert [f.path for f in files] == ["src/billing/FeatureGate.tsx", "src/todo/model.ts"]
    assert files[0].added == 2 and files[0].removed == 0
    assert files[1].added == 2 and files[1].removed == 1


def test_parse_diff_is_deterministic():
    assert parse_diff(DIFF) == parse_diff(DIFF)
