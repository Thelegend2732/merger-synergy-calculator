"""
Regenerate the README screenshots from a running app (Synopsys / Ansys case).

    streamlit run app.py                      # in another terminal
    python scripts/take_screenshots.py [url]  # default http://localhost:8501

Uses Playwright with the locally installed Microsoft Edge (`pip install playwright`, no browser
download needed). Images are written to docs/screenshots/.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
CASE = "Synopsys / Ansys (announced Jan 2024)"
CHART = '[data-testid="stPlotlyChart"]'


def settle(page, ms: int = 2500) -> None:
    """Wait for Streamlit to finish the current run."""
    page.wait_for_timeout(500)
    page.locator('[data-testid="stStatusWidget"]').wait_for(state="detached", timeout=30_000)
    page.wait_for_timeout(ms)


def open_tab(page, name: str) -> None:
    page.get_by_role("tab", name=name).click()
    settle(page, 1500)


def chart_with(page, title: str):
    """Visible Plotly chart whose title contains `title`."""
    return page.locator(CHART).filter(has_text=title).filter(visible=True).first


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True, args=["--lang=en-US"])
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1.25, locale="en-US")
        page.goto(URL)
        page.get_by_text("Merger Synergy Calculator").first.wait_for(timeout=60_000)
        settle(page)
        page.add_style_tag(content='[data-testid="stToolbar"], [data-testid="stDecoration"] {display: none;} .modebar {display: none !important;}')

        # Load the real-deal case from the sidebar
        page.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').first.click()
        page.get_by_role("option", name=CASE).click()
        page.get_by_role("button", name="Load preset").click()
        settle(page, 4000)

        open_tab(page, "Transaction Summary")
        page.screenshot(path=OUT / "summary.png")
        chart_with(page, "EPS bridge").screenshot(path=OUT / "eps_bridge.png")
        chart_with(page, "Contribution analysis").screenshot(path=OUT / "contribution.png")

        open_tab(page, "Comps & Football Field")
        chart_with(page, "Football field").screenshot(path=OUT / "football_field.png")

        open_tab(page, "Monte Carlo Risk")
        page.screenshot(path=OUT / "monte_carlo.png")
        chart_with(page, "EPS tornado").screenshot(path=OUT / "tornado.png")

        open_tab(page, "Projections & Sensitivity")
        chart_with(page, "Accretion / (dilution), Year").screenshot(path=OUT / "sensitivity.png")

        open_tab(page, "DCF Valuation")
        page.screenshot(path=OUT / "dcf.png")
        browser.close()
    print("Saved:", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
