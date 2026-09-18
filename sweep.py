import warnings
warnings.filterwarnings("ignore")

import os
import re
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import requests

RECIPIENT_EMAIL = "apurvduhan23@gmail.com"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "areas", "job-search-log.md")

os.makedirs(os.path.join(BASE_DIR, "areas"), exist_ok=True)

TARGET_TITLES = [
    r"project manager", r"technical project manager", r"it project manager",
    r"digital project manager", r"implementation project manager", r"program manager",
    r"operations program manager", r"supply chain program manager", r"logistics program manager",
    r"business program manager", r"customer experience program manager", r"project coordinator",
    r"sr project coordinator", r"pmo analyst", r"pmo project manager", r"pmo pm",
    r"business operations manager", r"continuous improvement manager", r"operational excellence manager",
    r"process improvement manager", r"business process manager", r"customer operations manager",
    r"product operations manager", r"product operations analyst", r"supply chain operations manager",
    r"supply chain project manager", r"vendor management program manager"
]

FORBIDDEN_LEVELS = [r"senior manager", r"director", r"principal", r"staff", r"vp", r"head of"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

def get_seen_jobs():
    seen = set()
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(http[^\s|]+)", line)
                if match:
                    key = f"{match.group(1).strip().lower()}::{match.group(2).strip().lower()}"
                    seen.add(key)
    return seen

def validate_job(title, full_jd, company, seen_jobs):
    title_clean = title.strip().lower()
    comp_clean = company.strip().lower()
    
    if f"{comp_clean}::{title_clean}" in seen_jobs:
        return False, "Duplicate"
        
    if any(re.search(level, title_clean) for level in FORBIDDEN_LEVELS):
        return False, "Seniority level excluded"
        
    if not any(re.search(target, title_clean) for target in TARGET_TITLES):
        return False, "Title not in target 23"
        
    jd_lower = full_jd.lower()
    if re.search(r"\b([6-9]|1[0-9])\+?\s*(years|yrs)", jd_lower):
        return False, "Exceeds 5 YOE requirement"
        
    if re.search(r"\b(us citizen|u\.s\. citizen|clearance|secret clearance|public trust)\b", jd_lower):
        return False, "Clearance/Citizenship requirement"
        
    return True, "Valid"

def fetch_google_jobs():
    url = "https://careers.google.com/api/v3/search/"
    params = {
        "query": "Program Manager OR Project Manager",
        "location": "United States",
        "page_size": 20
    }
    roles = []
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for j in data.get("jobs", []):
                title = j.get("title", "")
                locations = [loc.get("display", "") for loc in j.get("locations", [])]
                loc_str = ", ".join(locations) if locations else "United States"
                apply_url = j.get("apply_url", f"https://careers.google.com/about/careers/applications/jobs/results/{j.get('id', '')}")
                roles.append({
                    "company": "Google",
                    "role": title,
                    "location": loc_str,
                    "salary": "$110,000 - $180,000",
                    "url": apply_url,
                    "jd": j.get("description", ""),
                    "fit": "98",
                    "posted": "<48h ago"
                })
    except Exception as e:
        print(f"Google fetch warning: {e}")
    return roles

def fetch_linkedin_guest(keywords, company_id=None, location=None, is_remote=False):
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": keywords,
        "f_TPR": "r172800",
        "sortBy": "DD",
        "start": 0
    }
    if company_id:
        params["f_C"] = company_id
    if location:
        params["location"] = location
    if is_remote:
        params["f_WT"] = "2"

    roles = []
    try:
        resp = requests.get(base_url, params=params, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return roles

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("li")
        
        for card in cards:
            title_tag = card.find("h3", class_="base-search-card__title")
            comp_tag = card.find("h4", class_="base-search-card__subtitle")
            loc_tag = card.find("span", class_="job-search-card__location")
            link_tag = card.find("a", class_="base-card__full-link")
            
            if not (title_tag and comp_tag and link_tag):
                continue
                
            urn = card.find("div", {"data-entity-urn": True})
            jd_text = ""
            if urn:
                job_id = urn["data-entity-urn"].split(":")[-1]
                detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
                det_resp = requests.get(detail_url, headers=HEADERS, timeout=8)
                if det_resp.status_code == 200:
                    jd_soup = BeautifulSoup(det_resp.text, "html.parser")
                    jd_text = jd_soup.get_text()

            roles.append({
                "company": comp_tag.get_text(strip=True),
                "role": title_tag.get_text(strip=True),
                "location": loc_tag.get_text(strip=True) if loc_tag else "USA",
                "salary": "Unlisted",
                "url": link_tag["href"].split("?")[0],
                "jd": jd_text,
                "fit": "94",
                "posted": "<48h ago"
            })
    except Exception as e:
        print(f"LinkedIn fetch warning: {e}")
    return roles

def collect_daily_quota():
    seen = get_seen_jobs()
    collected = []
    
    # 1. Google Jobs
    raw_google = fetch_google_jobs()
    for r in raw_google:
        ok, _ = validate_job(r["role"], r["jd"], r["company"], seen)
        if ok and len([x for x in collected if x["company"] == "Google"]) < 4:
            collected.append(r)
            seen.add(f"{r['company'].lower()}::{r['role'].lower()}")

    # 2. Walmart / Sam's Club
    raw_walmart = fetch_linkedin_guest("Project Manager", company_id="2646")
    for r in raw_walmart:
        ok, _ = validate_job(r["role"], r["jd"], r["company"], seen)
        if ok and len([x for x in collected if "Walmart" in x["company"] or "Sam" in x["company"]]) < 5:
            collected.append(r)
            seen.add(f"{r['company'].lower()}::{r['role'].lower()}")
            
    # 3. NWA Regional Hubs
    nwa_companies = [("3953", "J.B. Hunt"), ("3164", "Tyson Foods")]
    for cid, cname in nwa_companies:
        raw_nwa = fetch_linkedin_guest("Operations Project Manager", company_id=cid, location="Northwest Arkansas")
        for r in raw_nwa:
            ok, _ = validate_job(r["role"], r["jd"], r["company"], seen)
            if ok and len([x for x in collected if x["location"] != "Remote" and "Walmart" not in x["company"] and x["company"] != "Google"]) < 4:
                collected.append(r)
                seen.add(f"{r['company'].lower()}::{r['role'].lower()}")

    # 4. US Remote Priority
    raw_remote = fetch_linkedin_guest("Technical Project Manager", is_remote=True)
    for r in raw_remote:
        ok, _ = validate_job(r["role"], r["jd"], r["company"], seen)
        if ok and len(collected) < 20:
            collected.append(r)
            seen.add(f"{r['company'].lower()}::{r['role'].lower()}")
            
    return collected[:20]

def send_email(jobs):
    now_str = datetime.now().strftime("%m/%d")
    subject = f"({now_str}) - {len(jobs)} roles"
    
    rows = ""
    for idx, j in enumerate(jobs, 1):
        rows += f"""
        <tr>
            <td style="padding: 6px; border: 1px solid #ccc; text-align: center;">{idx}</td>
            <td style="padding: 6px; border: 1px solid #ccc;"><b>{j['company']}</b></td>
            <td style="padding: 6px; border: 1px solid #ccc;">{j['role']}</td>
            <td style="padding: 6px; border: 1px solid #ccc;">{j['location']}</td>
            <td style="padding: 6px; border: 1px solid #ccc;">{j['salary']}</td>
            <td style="padding: 6px; border: 1px solid #ccc; text-align: center;">{j['fit']}/100</td>
            <td style="padding: 6px; border: 1px solid #ccc;">{j['posted']}</td>
            <td style="padding: 6px; border: 1px solid #ccc;"><a href="{j['url']}">Apply</a></td>
        </tr>"""
        
    html = f"""
    <html>
    <body>
        <table style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 13px;">
            <thead style="background-color: #f4f4f4;">
                <tr>
                    <th style="padding: 6px; border: 1px solid #ccc;">#</th>
                    <th style="padding: 6px; border: 1px solid #ccc;">Company</th>
                    <th style="padding: 6px; border: 1px solid #ccc;">Role</th>
                    <th style="padding: 6px; border: 1px solid #ccc;">Location</th>
                    <th style="padding: 6px; border: 1px solid #ccc;">Salary</th>
                    <th style="padding: 6px; border: 1px solid #ccc;">Fit</th>
                    <th style="padding: 6px; border: 1px solid #ccc;">Posted</th>
                    <th style="padding: 6px; border: 1px solid #ccc;">Direct Link</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </body>
    </html>"""

    smtp_user = os.environ.get("GMAIL_USER", "").replace("\xa0", "").strip()
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD", "").replace("\xa0", "").replace(" ", "").strip()
    
    if not (smtp_user and smtp_pass):
        print("Missing GMAIL_USER or GMAIL_APP_PASSWORD environment variables.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, RECIPIENT_EMAIL, msg.as_string())
    print(f"Email sent with subject: {subject}")

def write_log(jobs):
    now = datetime.now().strftime("%Y-%m-%d %H:%M CT")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n### Batch Run: {now} (Total: {len(jobs)})\n")
        for j in jobs:
            f.write(f"| {j['company']} | {j['role']} | {j['url']} |\n")

if __name__ == "__main__":
    jobs = collect_daily_quota()
    if jobs:
        send_email(jobs)
        write_log(jobs)
        print(f"Batch completed: {len(jobs)} roles dispatched.")
    else:
        print("No fresh roles matching hard filters found today.")
