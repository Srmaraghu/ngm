import scrapy
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from scrapy.crawler import CrawlerProcess
from scrapy.http import FormRequest
from bs4 import BeautifulSoup
from nepali.datetime import nepalidate
from ngm.ngscrape.settings import CONCURRENT_REQUESTS, DOWNLOAD_TIMEOUT, FILES_STORE
from ngm.utils.normalizer import (
    normalize_whitespace,
    normalize_date,
    nepali_to_roman_numerals,
    fix_parenthesis_spacing
)

OUTPUT_DIR = Path(FILES_STORE) if isinstance(FILES_STORE, str) else Path(FILES_STORE)
HIGH_COURT_DIR = OUTPUT_DIR / "court-cases" / "highcourts"
CHECKPOINT_FILE = HIGH_COURT_DIR / ".checkpoint.json"

# High courts in Nepal
HIGH_COURTS = [
    "biratnagarhc",
    "illamhc",
    "dhankutahc",
    "okhaldhungahc",
    "janakpurhc",
    "rajbirajhc",
    "birganjhc",
    "patanhc",
    "hetaudahc",
    "pokharahc",
    "baglunghc",
    "tulsipurhc",
    "butwalhc",
    "nepalgunjhc",
    "surkhethc",
    "jumlahc",
    "dipayalhc",
    "mahendranagarhc"
]


HIGH_COURTS = ["rajbirajhc"]


class HighCourtCasesSpider(scrapy.Spider):
    name = "high_court_cases"
    
    custom_settings = {
        # Retry configuration
        "CONCURRENT_REQUESTS": 2,
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429],
        "RETRY_PRIORITY_ADJUST": -1,
    }
    
    def __init__(self, court=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow filtering by specific court
        if court:
            self.courts = [court] if court in HIGH_COURTS else HIGH_COURTS
        else:
            self.courts = HIGH_COURTS
        
        self.processed_dates = self.load_checkpoint()
    
    def load_checkpoint(self):
        """Load set of already processed dates per court"""
        if CHECKPOINT_FILE.exists():
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('processed_dates', {})
        return {}
    
    def save_checkpoint(self, court, date_str):
        """Save a processed date to checkpoint for specific court"""
        if court not in self.processed_dates:
            self.processed_dates[court] = []
        
        if date_str not in self.processed_dates[court]:
            self.processed_dates[court].append(date_str)
        
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'processed_dates': self.processed_dates,
                'last_updated': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

    def start_requests(self):
        """Generate requests for all high courts for the past 5 years"""
        end_date = datetime.now().date() - timedelta(days=2)  # 2 days ago
        start_date = end_date - timedelta(days=5*365)  # 5 years ago
        
        for court in self.courts:
            current_date = end_date
            while current_date >= start_date:
                date_str = current_date.isoformat()
                
                # Skip if already processed for this court
                court_processed = self.processed_dates.get(court, [])
                if date_str in court_processed:
                    self.logger.debug(f"Skipping already processed date: {court} - {date_str}")
                    current_date -= timedelta(days=1)
                    continue
                
                # Convert to Nepali date
                try:
                    nepali_date = nepalidate.from_date(current_date)
                    pesi_date = f"{nepali_date.year:04d}%2F{nepali_date.month:02d}%2F{nepali_date.day:02d}"
                    
                    self.logger.info(f"Processing {court} - date: {date_str} -> BS {nepali_date.year}/{nepali_date.month:02d}/{nepali_date.day:02d}")
                    
                    # R1: First request to get bench list for this date
                    yield scrapy.Request(
                        url=f"https://supremecourt.gov.np/court/{court}/bench_list?pesi_date={pesi_date}",
                        callback=self.parse_bench_list,
                        meta={
                            'court': court,
                            'date_ad': date_str,
                            'nepali_year': nepali_date.year,
                            'nepali_month': nepali_date.month,
                            'nepali_day': nepali_date.day,
                            'hearing_date': f"{nepali_date.year:04d}{nepali_date.month:02d}{nepali_date.day:02d}"
                        },
                        dont_filter=True
                    )
                except Exception as e:
                    self.logger.error(f"Error converting date {date_str} for {court}: {e}")
                
                current_date -= timedelta(days=1)

    def parse_bench_list(self, response):
        """Parse the bench list from R1 response"""
        soup = BeautifulSoup(response.text, 'html.parser')
        
        court = response.meta['court']
        date_ad = response.meta['date_ad']
        hearing_date = response.meta['hearing_date']
        
        # Check if request was blocked by WAF
        if "The requested URL was rejected" in response.text or "support ID is:" in response.text:
            self.logger.error(f"Request blocked by WAF for {court} - {date_ad}. Try reducing CONCURRENT_REQUESTS or increasing DOWNLOAD_DELAY.")
            return
        
        # Debug: Log the response to see what we're getting
        self.logger.debug(f"Response URL: {response.url}")
        self.logger.debug(f"Response status: {response.status}")
        
        # Debug: Save HTML response for inspection
        debug_dir = HIGH_COURT_DIR / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_file = debug_dir / f"{court}_{date_ad}_bench_list.html"
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        self.logger.info(f"Saved debug HTML to {debug_file}")
        
        # Find the bench list table
        bench_table = soup.find('table', class_='table table-striped table-bordered table-hover')
        
        if not bench_table:
            # Debug: Try to find any tables
            all_tables = soup.find_all('table')
            self.logger.debug(f"Found {len(all_tables)} tables total")
            if all_tables:
                for idx, table in enumerate(all_tables):
                    self.logger.debug(f"Table {idx} classes: {table.get('class', [])}")
            
            self.logger.info(f"No bench list found for {court} - {date_ad}")
            self.save_checkpoint(court, date_ad)
            return
        
        # Extract bench information from table rows
        rows = bench_table.find('tbody').find_all('tr') if bench_table.find('tbody') else []
        
        benches = []
        for row in rows:
            # Skip summary rows (जम्माः)
            if 'जम्माः' in row.get_text():
                continue
            
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            
            # Extract bench_no and bench_id from onclick attribute
            onclick = row.get('onclick', '')
            if 'send_data' in onclick:
                # Parse: send_data('260823', '२', '20820904')
                import re
                match = re.search(r"send_data\('(\d+)',\s*'([^']+)',\s*'(\d+)'\)", onclick)
                if match:
                    bench_id = match.group(1)
                    bench_no = match.group(2)
                    
                    # Extract judge name
                    judge_cell = cells[1] if len(cells) > 1 else None
                    judge_name = normalize_whitespace(judge_cell.get_text()) if judge_cell else ""
                    
                    benches.append({
                        'bench_id': bench_id,
                        'bench_no': bench_no,
                        'judge_name': judge_name
                    })
        
        if not benches:
            self.logger.info(f"No benches found for {court} - {date_ad}")
            self.save_checkpoint(court, date_ad)
            return
        
        self.logger.info(f"Found {len(benches)} benches for {court} - {date_ad}")
        
        # R2: Request each bench's cause list
        for bench in benches:
            yield FormRequest(
                url=f"https://supremecourt.gov.np/court/{court}/cause_list_detail",
                formdata={
                    'bench_id': bench['bench_id'],
                    'bench_no': bench['bench_no'],
                    'hearing_date': hearing_date
                },
                callback=self.parse_cases,
                meta={
                    'court': court,
                    'date_ad': date_ad,
                    'nepali_year': response.meta['nepali_year'],
                    'nepali_month': response.meta['nepali_month'],
                    'nepali_day': response.meta['nepali_day'],
                    'bench_id': bench['bench_id'],
                    'bench_no': bench['bench_no'],
                    'judge_name': bench['judge_name']
                },
                dont_filter=True
            )
        
        # Mark date as processed after all benches are requested
        self.save_checkpoint(court, date_ad)

    def _clean_case_number(self, case_number_cell):
        """
        Clean case number by extracting only the main case number.
        Handles <br> tags and removes parenthetical information.
        
        Examples:
        - "082-AP-0023<br>" -> "082-AP-0023"
        - "081-WO-0257 ( सरल मार्ग )" -> "081-WO-0257"
        """
        # Replace <br> tags with space before extracting text
        for br in case_number_cell.find_all('br'):
            br.replace_with(' ')
        
        case_number = normalize_whitespace(case_number_cell.get_text())
        
        # Remove anything in parentheses (including the parentheses)
        import re
        cleaned = re.sub(r'\s*\([^)]*\)\s*', '', case_number)
        return cleaned.strip()
    
    def _parse_judges(self, judge_text):
        """
        Parse judge names into a list.
        Handles multiple judges separated by 'मा. न्या. श्री' prefix.
        
        Example:
        "मा. न्या. श्री महेन्द्रनाथ उपाध्यायमा. न्या. श्री नारायण प्रसाद रेग्मी"
        -> ["मा. न्या. श्री महेन्द्रनाथ उपाध्याय", "मा. न्या. श्री नारायण प्रसाद रेग्मी"]
        """
        if not judge_text:
            return []
        
        # Split by the judge prefix pattern
        import re
        # Split on 'मा. न्या. श्री' or 'मा.न्या.श्री' but keep the prefix
        parts = re.split(r'(मा\.?\s*न्या\.?\s*श्री)', judge_text)
        
        judges = []
        current_judge = ""
        
        for part in parts:
            if re.match(r'मा\.?\s*न्या\.?\s*श्री', part):
                # This is a prefix
                if current_judge:
                    judges.append(normalize_whitespace(current_judge))
                current_judge = part
            else:
                # This is a name
                current_judge += part
        
        # Add the last judge
        if current_judge:
            judges.append(normalize_whitespace(current_judge))
        
        return judges
    
    def _parse_lawyers(self, lawyers_text):
        """
        Parse lawyers field. Returns None if empty or '--'.
        Splits by '||' if present for plaintiff and defendant lawyers.
        """
        lawyers_text = normalize_whitespace(lawyers_text)
        
        if not lawyers_text or lawyers_text == '--':
            return None
        
        # Check if there are separate lawyers for plaintiff and defendant
        if '||' in lawyers_text:
            parts = lawyers_text.split('||', 1)
            return {
                'plaintiff_lawyers': normalize_whitespace(parts[0]),
                'defendant_lawyers': normalize_whitespace(parts[1])
            }
        
        return lawyers_text

    def parse_cases(self, response):
        """Parse the case details from R2 bench response"""
        soup = BeautifulSoup(response.text, 'html.parser')
        
        court = response.meta['court']
        date_ad = response.meta['date_ad']
        nepali_year = response.meta['nepali_year']
        nepali_month = response.meta['nepali_month']
        nepali_day = response.meta['nepali_day']
        bench_id = response.meta['bench_id']
        bench_no = response.meta['bench_no']
        judge_name = response.meta['judge_name']
        
        date_bs = f"{nepali_year:04d}-{nepali_month:02d}-{nepali_day:02d}"
        
        # Convert bench_no to Roman numerals
        bench_no_roman = nepali_to_roman_numerals(bench_no)
        
        # Parse judges into a list
        judges_list = self._parse_judges(judge_name)
        
        # Extract court name from header
        court_name_elem = soup.find('h3')
        court_name = normalize_whitespace(court_name_elem.get_text()) if court_name_elem else ""
        
        # Extract bench type (एकल इजलास, संयुक्त इजलास, etc.)
        bench_type_elem = soup.find('h4', string=lambda x: x and 'इजलास' in x)
        bench_type = normalize_whitespace(bench_type_elem.get_text()) if bench_type_elem else ""
        
        # Extract footer (इजलास अधिकृत info)
        footer_rows = soup.find_all('h5')
        footer_text = " | ".join([normalize_whitespace(elem.get_text()) for elem in footer_rows])
        
        # Find the case table
        case_table = soup.find('table', class_='table table-bordered table-hover')
        
        if not case_table:
            self.logger.warning(f"No case table found for {court} - bench {bench_no} on {date_ad}")
            return
        
        # Parse table rows (skip header)
        rows = case_table.find('tbody').find_all('tr', class_='data_row') if case_table.find('tbody') else []
        
        if not rows:
            self.logger.info(f"No cases found for {court} - bench {bench_no} on {date_ad}")
            return
        
        cases_found = 0
        for row in rows:
            cells = row.find_all('td')
            
            if len(cells) < 9:
                continue
            
            # Extract case data and normalize whitespace
            serial_no = nepali_to_roman_numerals(normalize_whitespace(cells[0].get_text()))
            division = normalize_whitespace(cells[1].get_text())
            registration_date = normalize_date(normalize_whitespace(cells[2].get_text()))
            case_type = normalize_whitespace(cells[3].get_text())
            
            # Clean case number (remove parenthetical info and handle <br> tags)
            case_number = self._clean_case_number(cells[4])
            
            # Parse parties (पक्ष || विपक्ष)
            parties = normalize_whitespace(cells[5].get_text())
            plaintiff = ""
            defendant = ""
            if "||" in parties:
                parts = parties.split("||", 1)
                plaintiff = normalize_whitespace(parts[0])
                defendant = normalize_whitespace(parts[1])
            else:
                plaintiff = parties
            
            # Lawyers (का. व्य. नाम) - parse and handle empty/-- values
            lawyers = self._parse_lawyers(cells[6].get_text())
            
            # Remarks (कैफियत)
            remarks = normalize_whitespace(cells[7].get_text())
            
            # Status (स्थिती)
            status_cell = cells[8]
            # Extract text preserving line breaks
            for br in status_cell.find_all('br'):
                br.replace_with('\n')
            status = normalize_whitespace(status_cell.get_text())
            
            # Skip if no case number
            if not case_number:
                continue
            
            # Create case data structure
            case_data = {
                'case_number': case_number,
                'court': court,
                'court_name': court_name,
                'date_ad': date_ad,
                'date_bs': date_bs,
                'bench_id': bench_id,
                'bench_no': bench_no_roman,
                'bench_type': bench_type,
                'judges': judges_list,
                'serial_no': serial_no,
                'division': division,
                'registration_date': registration_date,
                'case_type': case_type,
                'plaintiff': plaintiff,
                'defendant': defendant,
                'lawyers': lawyers,
                'remarks': remarks,
                'status': status,
                'footer': footer_text,
                'scraped_at': datetime.now().isoformat()
            }
            
            # Save case to file
            self.save_case(case_data)
            cases_found += 1
        
        self.logger.info(f"Saved {cases_found} cases for {court} - bench {bench_no} on {date_ad}")

    def save_case(self, case_data):
        """Save case data to JSON file organized by court, registration date, and case number"""
        court = case_data['court']
        case_number = case_data['case_number']
        date_bs = case_data['date_bs']
        registration_date = case_data['registration_date']
        
        # Use registration date for directory organization
        reg_date_dir = registration_date if registration_date else "unknown"
        
        # Sanitize case number for directory name
        case_dir_name = case_number.replace('/', '-').replace('\\', '-').strip()
        
        # Organize as: highcourts/<court>/<reg-date>/<case-number>/activity/<date>.json
        case_dir = HIGH_COURT_DIR / court / reg_date_dir / case_dir_name / "activity"
        filepath = case_dir / f"{date_bs}.json"
        
        # Skip if file already exists
        if filepath.exists():
            return
        
        # Create directory if it doesn't exist
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"Saved case: {case_number} for {court} on {date_bs}")


if __name__ == "__main__":
    import sys
    
    # Allow running for specific court: python high_court_cases.py dhankutahc
    court = sys.argv[1] if len(sys.argv) > 1 else None
    
    HIGH_COURT_DIR.mkdir(parents=True, exist_ok=True)
    process = CrawlerProcess({"LOG_LEVEL": "INFO"})
    process.crawl(HighCourtCasesSpider, court=court)
    process.start()
