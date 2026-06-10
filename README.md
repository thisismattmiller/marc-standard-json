# MARC Standard


This is a JSON representation of the [MARC Standards](https://www.loc.gov/marc/) using the [Avram Schema Language](https://format.gbv.de/schema/avram/specification)

[View the latest versions](latest/)

[View the versions by update](versions/)


[Use this interactive browser](https://thisismattmiller.github.io/marc-standard-json/) to see changes made for each update


----

To update:

Place the MARCDOCS XML folder in root dir and run:
```
cd converter
uv run python -m marc_avram.cli ../MARCDOCS/XML_files \
    --out ../versions \
    --validate avram_schema.yaml \
    --updates-html "location_of_updates_page.html"
```

`--updates-html` is the HTML file from the [updates page](https://www.loc.gov/marc/status.html)

or if not using uv:


```
cd converter
python3 -m venv .venv
source .venv/bin/activate     
pip install -e .
python -m marc_avram.cli ../MARCDOCS/XML_files \
    --out ../versions \
    --validate avram_schema.yaml \
    --updates-html "location_of_updates_page.html"
```
