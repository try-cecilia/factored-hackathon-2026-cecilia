"""The unique-key, chronology and as-of cross-table checks each count exactly the rows that break them."""
import duckdb

from data.quality import cross_table


def _warehouse():
    con = duckdb.connect()
    con.execute("CREATE TABLE branches (branch_id VARCHAR, branch_code VARCHAR)")
    con.execute("INSERT INTO branches VALUES ('B1', 'X1'), ('B2', 'X1'), ('B3', 'X3')")  # X1 repeated: 1 excess row
    con.execute("CREATE TABLE customers (customer_id VARCHAR, document_number VARCHAR, country VARCHAR, "
                "registration_date TIMESTAMP, registration_branch_id VARCHAR, last_updated TIMESTAMP)")
    con.execute("""INSERT INTO customers VALUES
        ('C1', 'D1', 'Argentina', '2024-03-01 10:00', 'B1', '2026-06-01'),
        ('C2', 'D2', 'Colombia', '2024-01-01 00:00', 'B1', '2027-06-15')""")  # C2 updated after the as-of date
    con.execute("CREATE TABLE products (product_id VARCHAR, customer_id VARCHAR, product_number VARCHAR, currency VARCHAR, "
                "opening_date DATE, last_updated TIMESTAMP)")
    con.execute("""INSERT INTO products VALUES
        ('P1', 'C1', '4000123', 'USD', '2024-03-10', '2026-06-01'),
        ('P2', 'C2', '4000123', 'USD', '2024-01-05', '2026-07-01'),
        ('P3', 'C2', '4000999', 'USD', '2024-01-05', '2026-06-17')""")  # P1/P2 share a number; P2 after as-of
    con.execute("CREATE TABLE transactions (transaction_id VARCHAR, transaction_date TIMESTAMP, process_date DATE, "
                "product_id VARCHAR, customer_id VARCHAR)")
    con.execute("""INSERT INTO transactions VALUES
        ('T1', '2024-03-05 12:00', '2024-03-05', 'P1', 'C1'),
        ('T2', '2024-03-01 09:00', '2024-03-01', 'P1', 'C1'),
        ('T3', '2024-03-10 23:59', '2024-03-11', 'P1', 'C1'),
        ('T4', '2026-06-17 08:00', '2026-06-17', 'P3', 'C2')""")
    # T1 and T2 predate P1's opening; T3 is on its opening day. T2 is an hour before C1 registered, on the same day,
    # which counts as on or after it: the checks compare calendar days, so none predates its customer's registration.
    con.execute("CREATE TABLE call_center_interactions (interaction_id VARCHAR, interaction_date TIMESTAMP, customer_id VARCHAR)")
    con.execute("""INSERT INTO call_center_interactions VALUES
        ('I1', '2024-02-28 10:00', 'C1'), ('I2', '2024-03-01 08:00', 'C1'), ('I3', '2025-01-01 00:00', 'C2')""")
    return con


def _results(con, table):
    return {r.check: (r.failed, r.total, r.severity) for r in cross_table(con, table)}


def test_unique_keys_count_excess_rows():
    con = _warehouse()
    assert _results(con, "branches")["cross:branch_code_unique"] == (1, 3, "warn")
    assert _results(con, "products")["cross:product_number_unique"] == (1, 3, "warn")
    assert _results(con, "customers")["cross:document_number_unique"] == (0, 2, "warn")


def test_movements_before_opening_or_registration_are_counted():
    got = _results(_warehouse(), "transactions")
    assert got["cross:tx_not_before_product_opening"] == (2, 4, "warn")
    assert got["cross:tx_not_before_customer_registration"] == (0, 4, "warn")


def test_contacts_before_registration_are_counted_by_calendar_day():
    got = _results(_warehouse(), "call_center_interactions")
    assert got["cross:contact_not_before_registration"] == (1, 3, "warn")


def test_rows_updated_after_the_as_of_date_are_counted():
    got = _results(_warehouse(), "transactions")  # as-of = the last processed day of transactions, 2026-06-17
    assert got["cross:products_not_updated_after_as_of"] == (1, 3, "warn")
    assert got["cross:customers_not_updated_after_as_of"] == (1, 2, "warn")


def test_a_check_waits_for_the_tables_it_reads():
    con = duckdb.connect()
    con.execute("CREATE TABLE transactions (transaction_id VARCHAR, transaction_date TIMESTAMP, process_date DATE, "
                "product_id VARCHAR, customer_id VARCHAR)")
    assert _results(con, "transactions") == {}
