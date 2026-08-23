from defintra.core.models.entities import EARSPattern
from defintra.core.requirements.ears import EARSEngine, EARSRequirement


def test_ears_render_patterns():
    # Ubiquitous
    req1 = EARSRequirement("System", "log all transactions", EARSPattern.UBIQUITOUS)
    assert req1.render() == "the System shall log all transactions."

    # Event-Driven
    req2 = EARSRequirement(
        "System",
        "send a confirmation email",
        EARSPattern.EVENT_DRIVEN,
        trigger="a new user registers",
    )
    assert req2.render() == "WHEN a new user registers, the System shall send a confirmation email."

    # State-Driven
    req3 = EARSRequirement(
        "System",
        "disable the submit button",
        EARSPattern.STATE_DRIVEN,
        state="processing a payment",
    )
    assert req3.render() == "WHILE processing a payment, the System shall disable the submit button."

    # Optional Feature
    req4 = EARSRequirement(
        "System",
        "calculate distance in miles",
        EARSPattern.OPTIONAL_FEATURE,
        feature="US locale is selected",
    )
    assert req4.render() == "WHERE US locale is selected, the System shall calculate distance in miles."

    # Unwanted Behavior
    req5 = EARSRequirement(
        "System",
        "display a network error dialog",
        EARSPattern.UNWANTED_BEHAVIOR,
        fault="connection timeout occurs",
    )
    assert req5.render() == "IF connection timeout occurs, THEN the System shall display a network error dialog."


def test_ears_parsing_and_classification():
    # Event parsing
    parsed1 = EARSEngine.classify_and_parse(
        "WHEN the student scans the QR code, the System shall mark attendance."
    )
    assert parsed1.pattern == EARSPattern.EVENT_DRIVEN
    assert parsed1.trigger == "the student scans the QR code"
    assert parsed1.system_response == "mark attendance"

    # Unwanted parsing
    parsed2 = EARSEngine.classify_and_parse(
        "IF invalid PIN is entered 3 times, THEN the System shall lock the account."
    )
    assert parsed2.pattern == EARSPattern.UNWANTED_BEHAVIOR
    assert parsed2.fault == "invalid PIN is entered 3 times"


def test_ears_validation():
    valid, issues = EARSEngine.validate_ears("The System shall encrypt user passwords.")
    assert valid is True
    assert len(issues) == 0

    invalid, issues = EARSEngine.validate_ears("The System should maybe store data.")
    assert invalid is False
    assert any("shall" in issue for issue in issues)
