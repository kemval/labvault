"""A stand-in for the openFDA API so import tests never touch the network."""


def record(n, reason="Failed dissolution specifications", status="Ongoing"):
    return {
        "recall_number": f"D-{n:04d}-2024",
        "product_description": f"Product {n} Tablets 10 mg. Rx only",
        "recalling_firm": f"Firm {n}",
        "reason_for_recall": reason,
        "classification": "Class II",
        "status": status,
        "recall_initiation_date": "20240115",
    }


class FakeResponse:
    def __init__(self, records):
        self._records = records

    def raise_for_status(self):
        pass

    def json(self):
        return {"results": self._records}


def serve(monkeypatch, records, before_return=None):
    """Make seed.requests.get return `records`; count calls."""
    import seed
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        if before_return:
            before_return()
        return FakeResponse(list(records))

    monkeypatch.setattr(seed.requests, "get", fake_get)
    return calls
