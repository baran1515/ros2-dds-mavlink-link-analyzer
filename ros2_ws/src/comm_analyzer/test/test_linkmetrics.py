from comm_analyzer.linkmetrics import LossCounter, Summary


def test_loss_counter_wrap_32bit():
    c = LossCounter(bits=32)
    for s in (2**32 - 2, 2**32 - 1, 1):
        c.update(s)
    assert c.lost == 1


def test_summary_empty():
    assert Summary.of([]).n == 0
