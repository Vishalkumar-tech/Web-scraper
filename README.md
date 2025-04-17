# Web-scraper
📊 U.S. Largest Companies Data Scraper
This project is a simple Python script that scrapes the list of the largest companies in the United States by revenue from Wikipedia using BeautifulSoup and requests. 
It then organizes the data into a structured format using pandas and exports it to a CSV file for further analysis.

🚀 What This Script Does
Connects to Wikipedia's page listing the largest U.S. companies by revenue.
Parses the HTML content to find the relevant table using BeautifulSoup.
Extracts the headers and rows from the table.
Cleans and structures the data.
Saves the extracted data to a CSV file.
Includes a few additional explorations using regex and link extraction.

🛠 Requirements
Python 3.x
Libraries used:
requests
beautifulsoup4
pandas
re (Python's built-in regex module)

✨ Sample Output (Preview)
Rank	Name	Industry	Revenue (USD millions)	Employees	Headquarters Location
1	Walmart	Retail	611,289	2,100,000	Bentonville, Arkansas
2	Amazon	Retail	513,983	1,540,000	Seattle, Washington

📚 Learnings
Web scraping using BeautifulSoup and requests
Parsing and cleaning HTML tables
Creating and exporting DataFrames with pandas
Using regular expressions to find HTML elements dynamically

📬 Contact
Feel free to contribute, suggest improvements, or ask questions via Issues or Pull Requests!
