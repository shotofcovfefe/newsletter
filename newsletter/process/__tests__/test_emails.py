import pytest
from bs4 import BeautifulSoup
from newsletter.process.emails import is_html, strip_html, remove_urls


@pytest.fixture
def sample_html():
    """Fixture to load a full HTML file for testing."""
    with open("./newsletter/process/__tests__/resources/test.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize(
    "text, expected",
    [
        ("<html><body>Hello</body></html>", True),  # Full HTML document
        ("<!DOCTYPE html><html><head></head><body>Content</body></html>", True),  # Doctype declaration
        ("<p>This is a paragraph.</p>", True),  # HTML element
        ("<div class='container'>Content</div>", True),  # Common HTML structure
        ("Some plain text with no tags.", False),  # Plain text
        ("Just a sentence. No HTML here.", False),  # No HTML
        ("< unknown>", False),  # Not a valid HTML tag
    ],
)
def test_is_html(text, expected):
    assert is_html(text) == expected


@pytest.mark.parametrize(
    "html, expected_text",
    [
        ("<html><body>Hello, <b>world</b>!</body></html>", "Hello, #world#!"),
        ("<div>Test <span>content</span></div>", "Test #content"),
        ("<p>This is a <strong>test</strong> paragraph.</p>", "This is a #test# paragraph."),
        ("No HTML here.", "No HTML here."),
        ("<ul><li>Item 1</li><li>Item 2</li></ul>", "Item 1#Item 2"),
        ("", ""),
    ],
)
def test_strip_html(html, expected_text):
    assert strip_html(html) == expected_text


def test_is_html_large(sample_html):
    assert is_html(sample_html) is True


def test_strip_html_is_smaller(sample_html):
    assert len(strip_html(sample_html)) < len(sample_html)


@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        ("Visit https://example.com for more info.", "Visit  for more info."),  # Simple case
        ("Check this link: https://example.com/page", "Check this link:"),  # Inline URL
        ("https://example.com is a great site.", "is a great site."),  # URL at start of sentence
        ("Follow us at http://twitter.com/someuser!", "Follow us at"),  # HTTP version
        ("Here's a list:\nhttps://site.com\nhttps://example.com", "Here's a list:"),  # Multiple URLs
        ("Plain text with no links.", "Plain text with no links."),  # No URLs
        ("Multiple links https://a.com text https://b.com", "Multiple links  text"),  # Multiple inline
        ("Trailing URL https://test.com.", "Trailing URL"),  # URL at the end
    ],
)
def test_remove_urls(input_text, expected_output):
    assert remove_urls(input_text) == expected_output
