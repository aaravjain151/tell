"""Per-pattern tests for the intent families, including negatives that matter for older callers."""
import pytest

from doublespeak import pipeline
from doublespeak.signals import intent


def fired(text):
    tells, _ = intent.detect(text)
    return {t.name for t in tells if t.family == "intent" and t.applicable and t.score > 0}


@pytest.mark.parametrize("text,family", [
    ("Grandma, I was in an accident and I need help right away", "emergency"),
    ("We have your grandson, this is a kidnapping, do not call anyone", "emergency"),
    ("Pay the ransom or you will not see him again", "emergency"),
    ("Grandpa I am in serious trouble and I need you to listen", "emergency"),
    ("Please, I'm in trouble. Don't tell mom.", "emergency"),
    ("He is in jail and we need to post bail tonight", "emergency"),
    ("She was rushed to the hospital and needs surgery money", "emergency"),
    ("You are going to be arrested unless you act", "authority_threat"),
    ("There is an arrest warrant for you under your name", "authority_threat"),
    ("We will send the police to your house today", "authority_threat"),
    ("This is a federal crime and you will face charges", "authority_threat"),
    ("Legal action against you will be taken tomorrow", "authority_threat"),
    ("Read me the gift card number and the scratch off code", "payment_rails"),
    ("Buy steam cards and read me the numbers", "payment_rails"),
    ("Please wire transfer it through Western Union", "payment_rails"),
    ("Send the money to this account today", "payment_rails"),
    ("I also need your routing number to verify", "credential_ask"),
    ("Confirm your social security and bank account number", "credential_ask"),
    ("What is the security code on the back of your card", "credential_ask"),
])
def test_pattern_fires(text, family):
    assert family in fired(text)


@pytest.mark.parametrize("text", [
    "Hi grandma, I'm in trouble with my homework, can you help me with fractions later",
    "Hello, the hospital called about your prescription, it is ready for pickup at the pharmacy",
    "This is the pharmacy. Your hospital discharge medication is ready, no payment is due today",
    "I called the police about the noise last night but they never came",
    "The accident report for the fender bender is ready, come by the office tomorrow",
    "My lawyer says the lawsuit against the contractor is going well, so don't worry",
    "Hi, this is your bank. We will never ask for your PIN or password on a phone call",
    "We do not ask for your card number or your social security number by phone, ever",
    "Remember, the IRS will never ask you to pay with gift cards or wire transfer",
    "Never share your security code on the back of your card with anyone who calls you",
    "I'm bailing on dinner tonight, I'm exhausted, see you Sunday",
    "Grandpa the game went into overtime, our team is in trouble but we might win",
])
def test_benign_does_not_trip(text):
    assert fired(text) == set(), (text, fired(text))


def test_single_new_family_hit_is_not_a_scam_verdict():
    v = pipeline.analyze(None, "Hello, it is Anna. I was in an accident last week but I am fine now and wanted to tell you about the repair bill, call me back whenever you like.")
    assert v.tier != "scam"


def test_emergency_plus_payment_is_scam():
    v = pipeline.analyze(None, "Grandma it's me, I'm in serious trouble, I was in an accident. Please buy gift cards right now and don't tell mom.")
    assert v.tier == "scam"
