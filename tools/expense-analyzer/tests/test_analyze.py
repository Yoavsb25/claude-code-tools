import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze  # noqa: E402


def make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE merchant_rules (merchant_key TEXT, category TEXT);
        CREATE TABLE categories (key TEXT, name TEXT, counts INTEGER);
        CREATE TABLE own_identifiers (identifier TEXT);
        CREATE TABLE transactions (account_id TEXT, external_id TEXT, date TEXT, amount REAL,
            currency TEXT, merchant_key TEXT, merchant_name TEXT, category TEXT, pot_move INTEGER,
            counterparty TEXT);
        INSERT INTO categories VALUES ('groceries','Groceries',1), ('general','General',1),
            ('investment','Investment',1), ('income','Income',0);
        INSERT INTO merchant_rules VALUES ('t212','investment');
        INSERT INTO own_identifiers VALUES ('me');
    """)
    conn.executemany("INSERT INTO transactions VALUES ('monzo',?,?,?,'GBP',?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_monzo_collects_left_out_payments_and_counts_general(tmp_path):
    db = tmp_path / "w.db"
    make_db(db, [
        ("1", "2026-11-02", -20.0, "ocado", "Ocado", "groceries", 0, None),
        ("2", "2026-11-03", -36.0, "cafe", "Corner Cafe", "general", 0, None),
        ("3", "2026-11-04", -500.0, "t212", "Trading 212", "general", 0, None),
        ("4", "2026-11-05", -50.0, "pot", "Savings pot", "groceries", 1, None),
        ("5", "2026-11-06", -15.0, "x", "Own transfer", "groceries", 0, "me"),
        ("6", "2026-11-07", -9.0, "shop", "Shop", "groceries", 0, None),
        ("7", "2026-11-08", 9.0, "shop", "Shop", "groceries", 0, None),
        ("8", "2026-11-09", 0.0, "goog", "Google", "general", 0, None),
        ("9", "2026-10-30", -99.0, "t212", "Trading 212", "general", 0, None),
    ])
    excluded = []
    txs = analyze.load_monzo_transactions("2026-11", db_path=str(db), excluded=excluded)
    assert {(t["merchant"], t["category"]) for t in txs} == {
        ("Ocado", "Groceries"), ("Corner Cafe", "Uncategorised")}
    reasons = {e["merchant"]: e["reason"] for e in excluded}
    assert reasons == {"Trading 212": "not spending (Investment)", "Savings pot": "pot move",
                       "Own transfer": "transfer between own accounts", "Shop": "refunded 08 Nov"}


def test_load_report_totals_reads_saved_report(tmp_path):
    report = tmp_path / "expense-report-2026-10.md"
    report.write_text(
        "# Expense Report — October 2026\n\n**Total spent:** £1,200.00 (+£50.00 vs September)  \n\n"
        "## By Category\n\n| Category | Total | vs September | # | Avg/txn | Avg/month |\n"
        "|---|---:|---:|--:|--:|--:|\n| Groceries | £400.00 | +£100.00 | 20 | £20.00 | £350.00 |\n"
        "| Charity | £25.00 | +£25.00 | 1 | £25.00 | £5.00 |\n\n---\n\n## Top 10 Transactions\n\n"
        "| Date | Merchant | Category | Amount |\n| 12 Oct | Theatre | Entertainment | £150.00 |\n")
    totals, total = analyze.load_report_totals(report)
    assert totals == {"Groceries": 400.0, "Charity": 25.0}
    assert total == 1200.0


def test_month_fraction():
    assert analyze.month_fraction("2026-11", date(2026, 11, 27)) == 0.9
    assert analyze.month_fraction("2026-10", date(2026, 11, 27)) == 1.0


def test_possibly_missing_pro_rates_and_skips_small_or_irregular():
    avg = {"Groceries": 400.0, "Bills": 30.0, "Trips": 150.0, "Eating out": 300.0}
    got = analyze.possibly_missing({"Groceries": 200.0, "Eating out": 280.0}, avg, 0.9)
    assert [c for c, _, _ in got] == ["Groceries"]
