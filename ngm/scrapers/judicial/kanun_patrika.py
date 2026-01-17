#!/usr/bin/env python3
import os
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.pipelines.files import FilesPipeline
from ..config import FILES_STORE, DEFAULT_SETTINGS
from botocore.client import Config


class PDFPipeline(FilesPipeline):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def file_path(self, request, response=None, info=None, *, item=None):
        metadata = item.get('metadata', {})
        file_id = request.url.split("/")[-1].replace(".pdf", "")
        
        if metadata:
            year = metadata.get('year', '')
            month = metadata.get('month', '')
            volume = metadata.get('volume', '')
            issue = metadata.get('issue', '')
            return f"{year} {month} भाग {volume} अंक {issue} - {file_id}.pdf"
        
        return f"{file_id}.pdf"

    def item_completed(self, results, item, info):
        for ok, result in results:
            if ok:
                file_path = result['path']
                print(f"Downloaded: {file_path}")
            else:
                print(f"Failed: {item['file_urls'][0]}")
        return item


class NepalLawJournalSpider(scrapy.Spider):
    name = "nepal_law_journal"
    start_urls = ["https://supremecourt.gov.np/web/nkpold"]
    custom_settings = {
        **DEFAULT_SETTINGS,
        "ITEM_PIPELINES": {PDFPipeline: 1},
        "FILES_STORE": os.path.join(FILES_STORE, "supreme-court/kanun-patrika/"),
    }

    def parse(self, response):
        rows = response.xpath('//div[@class="content-wrap"]//table[@class="table-striped"]//tbody/tr')
        print(f"Found {len(rows)} rows")
        
        for row in rows:
            year = row.xpath('.//td[2]/text()').get('').strip()
            month = row.xpath('.//td[3]/text()').get('').strip()
            volume = row.xpath('.//td[4]/text()').get('').strip()
            issue = row.xpath('.//td[5]/text()').get('').strip()
            pdf_url = row.xpath('.//a[contains(@href, ".pdf")]/@href').get()
            
            if pdf_url:
                yield {
                    "file_urls": [response.urljoin(pdf_url)],
                    "metadata": {
                        "year": year,
                        "month": month,
                        "volume": volume,
                        "issue": issue
                    }
                }


if __name__ == "__main__":
    process = CrawlerProcess({"LOG_LEVEL": "INFO"})
    process.crawl(NepalLawJournalSpider)
    process.start()
