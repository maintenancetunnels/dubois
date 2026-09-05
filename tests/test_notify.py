from dubois.notify import QueryNotifyPrint
from dubois.result import QueryResult, QueryStatus


def test_claimed_count_is_per_instance_not_global():
    first = QueryNotifyPrint()
    second = QueryNotifyPrint()
    hit = QueryResult("a", "GitHub", "https://github.com/a", QueryStatus.CLAIMED)
    first.update(hit)
    first.update(hit)
    second.update(hit)
    assert first.claimed_count == 2
    assert second.claimed_count == 1
