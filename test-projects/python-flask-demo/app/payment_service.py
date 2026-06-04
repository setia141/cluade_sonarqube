import os
import requests


PAYMENT_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:8081")


# python:S5754 — bare except swallows all exceptions including KeyboardInterrupt
def charge(customer_id: str, amount: float) -> dict:
    try:
        response = requests.post(
            f"{PAYMENT_URL}/charge",
            json={"customerId": customer_id, "amount": amount},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except:                          # S5754: bare except
        return {"status": "error"}


# python:S1481 — unused local variable
def get_balance(customer_id: str) -> float:
    debug_label = f"balance_check_{customer_id}"   # S1481: never used
    response = requests.get(
        f"{PAYMENT_URL}/balance/{customer_id}",
        timeout=5,
    )
    response.raise_for_status()
    return response.json().get("balance", 0.0)


# python:S2077 — SQL built by string concatenation
def find_transactions(customer_id: str) -> list:
    import sqlite3
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    # S2077: SQL injection via string formatting
    cursor.execute(f"SELECT * FROM transactions WHERE customer_id = '{customer_id}'")
    return cursor.fetchall()
