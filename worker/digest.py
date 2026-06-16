"""Build the daily digest (email HTML + Telegram text) from the day's results
and the current month's LLM spend. Pure formatter — unit-tested directly.
"""


def build_digest(*, jobs: list[dict], budget: dict, date: str,
                 cap: float = 10.0) -> dict:
    n = len(jobs)
    html = [f"<b>{date} — Job Agent digest</b>",
            f"{n} new match(es) added to your Notion Career Hub."]
    text = [f"{date} — Job Agent digest", f"{n} new matches in Notion:"]

    for j in jobs[:25]:
        title = j.get("title", "Untitled")
        url = j.get("notion_page_url") or j.get("url") or ""
        visa = j.get("visa", "")
        score = j.get("score")
        score_s = f" (score {score})" if score else ""
        html.append(f'• <a href="{url}">{title}</a> — {visa}{score_s}')
        text.append(f"- {title} [{visa}]{score_s} {url}")

    a = float(budget.get("a", 0.0))
    b = float(budget.get("b", 0.0))
    foot = f"LLM spend this month — key A ${a:.2f}/{cap:g}, key B ${b:.2f}/{cap:g}."
    html.append(f"<i>{foot}</i>")
    text.append(foot)

    return {
        "subject": f"Job Agent — {n} new match(es) [{date}]",
        "html": "<br>".join(html),
        "text": "\n".join(text),
        "telegram": "\n".join(text),
    }
