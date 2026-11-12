from voice_talk.chunker import Chunker


def test_sentence_boundaries_emit_early():
    c = Chunker()
    assert c.feed("Hello there. How are") == ["Hello there."]
    assert c.pending == "How are"
    assert c.feed(" you today? Fine") == ["How are you today?"]
    assert c.flush() == ["Fine"]


def test_clause_boundary_when_long_enough():
    c = Chunker(min_clause_chars=18)
    assert c.feed("When I got home yesterday, I was") == ["When I got home yesterday,"]
    assert c.feed("Yes, ok ") == []  # short clause is not split


def test_abbreviations_and_initials_do_not_split():
    c = Chunker()
    out = c.feed("Dr. Smith met Mr. Jones and J. K. Rowling at 5 p.m. today. Next")
    assert out == ["Dr. Smith met Mr. Jones and J. K. Rowling at 5 p.m. today."]


def test_decimals_and_trailing_period_wait():
    c = Chunker()
    assert c.feed("It costs 3.") == []  # may become 3.5
    assert c.feed("5 dollars. Ok") == ["It costs 3.5 dollars."]
    assert Chunker().feed("version 2.10.3 is out. go") == ["version 2.10.3 is out."]


def test_very_long_sentence_is_split():
    c = Chunker(max_chars=60)
    words = " ".join(["word"] * 40)
    out = c.feed(words)
    assert out and all(len(x) <= 60 for x in out)
    rest = c.flush()
    assert " ".join(out + rest).split() == words.split()


def test_flush_on_stop_releases_remainder_and_empties():
    c = Chunker()
    c.feed("unfinished thought without punctuation")
    assert c.flush() == ["unfinished thought without punctuation"]
    assert c.flush() == [] and c.pending == ""


def test_cjk_terminators_need_no_space():
    assert Chunker().feed("今天天气很好。我们去公园吧！还有") == ["今天天气很好。", "我们去公园吧！"]


def test_quotes_after_terminator_stay_with_sentence():
    assert Chunker().feed('He said "stop!" Then left. ') == ['He said "stop!"', "Then left."]


def test_min_chunk_chars_merges_short_sentences_after_the_first_chunk():
    c = Chunker(min_chunk_chars=40)
    out = c.feed("Hello there, my friend. Ok. Yes. The weather is lovely today, isn't it? Bye. ")
    assert out[0] == "Hello there, my friend."  # the first chunk is never held back (fast start)
    assert out[1] == "Ok. Yes. The weather is lovely today, isn't it?"  # short sentences ride with the next one
    assert c.flush() == ["Bye."]  # flush releases whatever is left
    assert "".join(" ".join(out).split()) == "".join("Hello there, my friend. Ok. Yes. The weather is lovely today, isn't it?".split())


def test_min_chunk_chars_waits_for_more_text_and_default_is_unchanged():
    c = Chunker(min_chunk_chars=40)
    assert c.feed("First one is long enough. Short. ") == ["First one is long enough."]
    assert c.pending == "Short. "  # held until more text arrives
    assert c.feed("And here is a much longer follow up sentence. ") == ["Short. And here is a much longer follow up sentence."]
    d = Chunker()
    assert d.feed("First. Short. Third. ") == ["First.", "Short.", "Third."]  # no merging unless asked
