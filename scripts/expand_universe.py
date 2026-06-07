#!/usr/bin/env python3
"""Expand nifty500.csv to include a representative Nifty 500 stock list.

Run once to regenerate the universe file with more symbols.
Source: NSE India Nifty 500 index constituents (as of June 2026).
Only adds symbols not already in the file.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

UNIVERSE_PATH = "data/universe/nifty500.csv"

# Additional Nifty 500 symbols not in the current 108-symbol CSV.
# Columns: symbol, company_name, sector, industry, isin, exchange, breeze_code, lot_size
# breeze_code: NSE symbols often differ from Breeze codes (use symbol as default).
ADDITIONAL_SYMBOLS = [
    # ── Financial Services ─────────────────────────────────────────────────────
    ("AXISBANK",    "Axis Bank Ltd",                   "Financial Services", "Banks",                       "INE238A01034", "NSE", "AXSBNK",  1),
    ("KOTAKBANK",   "Kotak Mahindra Bank Ltd",          "Financial Services", "Banks",                       "INE237A01028", "NSE", "KOTAKM",  1),
    ("SBIN",        "State Bank of India",              "Financial Services", "Banks",                       "INE062A01020", "NSE", "SBIN",    1),
    ("BAJFINANCE",  "Bajaj Finance Ltd",                "Financial Services", "Diversified Financials",      "INE296A01024", "NSE", "BJFIN",   1),
    ("BAJAJFINSV",  "Bajaj Finserv Ltd",                "Financial Services", "Diversified Financials",      "INE918I01026", "NSE", "BJFNSV",  1),
    ("HDFCLIFE",    "HDFC Life Insurance Co Ltd",       "Financial Services", "Insurance",                   "INE795G01014", "NSE", "HDFCLF",  1),
    ("SBILIFE",     "SBI Life Insurance Co Ltd",        "Financial Services", "Insurance",                   "INE123W01016", "NSE", "SBILIF",  1),
    ("ICICIPRULI",  "ICICI Prudential Life Insurance",  "Financial Services", "Insurance",                   "INE726G01019", "NSE", "ICICPR",  1),
    ("MUTHOOTFIN",  "Muthoot Finance Ltd",              "Financial Services", "Consumer Finance",            "INE414G01012", "NSE", "MUTHOF",  1),
    ("CHOLAFIN",    "Cholamandalam Investment",         "Financial Services", "Consumer Finance",            "INE121A01024", "NSE", "CHOLFN",  1),
    ("PNB",         "Punjab National Bank",             "Financial Services", "Banks",                       "INE160A01022", "NSE", "PNB",     1),
    ("BANKBARODA",  "Bank of Baroda",                   "Financial Services", "Banks",                       "INE028A01039", "NSE", "BNKBRD",  1),
    ("CANBK",       "Canara Bank",                      "Financial Services", "Banks",                       "INE476A01022", "NSE", "CANBK",   1),
    ("UNIONBANK",   "Union Bank of India",              "Financial Services", "Banks",                       "INE692A01016", "NSE", "UNIBNK",  1),
    ("FEDERALBNK",  "Federal Bank Ltd",                 "Financial Services", "Banks",                       "INE171A01029", "NSE", "FEDBNK",  1),
    ("IDFCFIRSTB",  "IDFC First Bank Ltd",              "Financial Services", "Banks",                       "INE092T01019", "NSE", "IDFCFB",  1),
    ("RBLBANK",     "RBL Bank Ltd",                     "Financial Services", "Banks",                       "INE976G01028", "NSE", "RBLBNK",  1),
    ("MANAPPURAM", "Manappuram Finance Ltd",            "Financial Services", "Consumer Finance",            "INE522D01027", "NSE", "MANAPR",  1),
    ("LICHSGFIN",   "LIC Housing Finance Ltd",          "Financial Services", "Mortgage Finance",            "INE115A01026", "NSE", "LICHSG",  1),
    ("PNBHOUSING",  "PNB Housing Finance Ltd",          "Financial Services", "Mortgage Finance",            "INE572E01012", "NSE", "PNBHSN",  1),

    # ── Information Technology ─────────────────────────────────────────────────
    ("WIPRO",       "Wipro Ltd",                        "Information Technology", "IT Services & Consulting","INE075A01022", "NSE", "WIPRO",   1),
    ("HCLTECH",     "HCL Technologies Ltd",             "Information Technology", "IT Services & Consulting","INE860A01027", "NSE", "HCLTECH", 1),
    ("TECHM",       "Tech Mahindra Ltd",                "Information Technology", "IT Services & Consulting","INE669C01036", "NSE", "TECHM",   1),
    ("LTIM",        "LTIMindtree Ltd",                  "Information Technology", "IT Services & Consulting","INE214T01019", "NSE", "LTIMND",  1),
    ("MPHASIS",     "Mphasis Ltd",                      "Information Technology", "IT Services & Consulting","INE356A01018", "NSE", "MPHSIS", 1),
    ("PERSISTENT",  "Persistent Systems Ltd",           "Information Technology", "IT Services & Consulting","INE262H01021", "NSE", "PERSYS",  1),
    ("COFORGE",     "Coforge Ltd",                      "Information Technology", "IT Services & Consulting","INE591G01017", "NSE", "COFORG",  1),
    ("ORACLE",      "Oracle Financial Services",        "Information Technology", "IT Services & Consulting","INE881D01027", "NSE", "ORACLF",  1),
    ("KPIT",        "KPIT Technologies Ltd",            "Information Technology", "IT Services & Consulting","INE058I01021", "NSE", "KPIT",    1),
    ("TATAELXSI",   "Tata Elxsi Ltd",                   "Information Technology", "IT Services & Consulting","INE670A01012", "NSE", "TATAEL",  1),
    ("OFSS",        "Oracle Financial Services",        "Information Technology", "IT Services & Consulting","INE881D01027", "NSE", "OFSS",    1),
    ("HEXAWARE",    "Hexaware Technologies Ltd",        "Information Technology", "IT Services & Consulting","INE093A01033", "NSE", "HEXAWRE", 1),
    ("CYIENT",      "Cyient Ltd",                       "Information Technology", "IT Services & Consulting","INE136B01020", "NSE", "CYIENT",  1),

    # ── Consumer Goods / FMCG ─────────────────────────────────────────────────
    ("NESTLEIND",   "Nestle India Ltd",                 "Consumer Goods",    "Packaged Foods",              "INE239A01024", "NSE", "NESTLND", 1),
    ("BRITANNIA",   "Britannia Industries Ltd",         "Consumer Goods",    "Packaged Foods",              "INE216A01030", "NSE", "BRITIN",  1),
    ("GODREJCP",    "Godrej Consumer Products Ltd",     "Consumer Goods",    "Household Products",          "INE102D01028", "NSE", "GODRCP",  1),
    ("DABUR",       "Dabur India Ltd",                  "Consumer Goods",    "Personal Products",           "INE016A01026", "NSE", "DABUR",   1),
    ("MARICO",      "Marico Ltd",                       "Consumer Goods",    "Personal Products",           "INE196A01026", "NSE", "MARICO",  1),
    ("COLPAL",      "Colgate-Palmolive (India) Ltd",    "Consumer Goods",    "Household Products",          "INE259A01022", "NSE", "COLPAL",  1),
    ("EMAMILTD",    "Emami Ltd",                        "Consumer Goods",    "Personal Products",           "INE548C01032", "NSE", "EMAMI",   1),
    ("GILLETTE",    "Gillette India Ltd",               "Consumer Goods",    "Personal Products",           "INE322A01010", "NSE", "GILIND",  1),
    ("GODREJIND",   "Godrej Industries Ltd",            "Consumer Goods",    "Diversified",                 "INE233B01017", "NSE", "GODIND",  1),
    ("VBL",         "Varun Beverages Ltd",              "Consumer Goods",    "Beverages",                   "INE200L01014", "NSE", "VBL",     1),
    ("RADICO",      "Radico Khaitan Ltd",               "Consumer Goods",    "Beverages",                   "INE944F01028", "NSE", "RADICO",  1),
    ("TATACONSUM",  "Tata Consumer Products Ltd",       "Consumer Goods",    "Packaged Foods",              "INE192A01025", "NSE", "TATCON",  1),

    # ── Healthcare ─────────────────────────────────────────────────────────────
    ("SUNPHARMA",   "Sun Pharmaceutical Industries",   "Healthcare",        "Pharmaceuticals",             "INE044A01036", "NSE", "SUNPHA",  1),
    ("DRREDDY",     "Dr. Reddys Laboratories Ltd",     "Healthcare",        "Pharmaceuticals",             "INE089A01023", "NSE", "DRRDDY",  1),
    ("CIPLA",       "Cipla Ltd",                        "Healthcare",        "Pharmaceuticals",             "INE059A01026", "NSE", "CIPLA",   1),
    ("APOLLOHOSP",  "Apollo Hospitals Enterprise Ltd", "Healthcare",        "Health Care Facilities",      "INE437A01024", "NSE", "APLHSP",  1),
    ("BIOCON",      "Biocon Ltd",                       "Healthcare",        "Biotechnology",               "INE376G01013", "NSE", "BIOCON",  1),
    ("ALKEM",       "Alkem Laboratories Ltd",           "Healthcare",        "Pharmaceuticals",             "INE540L01014", "NSE", "ALKEM",   1),
    ("IPCALAB",     "IPCA Laboratories Ltd",            "Healthcare",        "Pharmaceuticals",             "INE571A01020", "NSE", "IPCALA",  1),
    ("LALPATHLAB",  "Dr. Lal Path Labs Ltd",            "Healthcare",        "Health Care Facilities",      "INE600L01024", "NSE", "DRLAPL",  1),
    ("METROPOLIS",  "Metropolis Healthcare Ltd",        "Healthcare",        "Health Care Facilities",      "INE112L01020", "NSE", "METRPO",  1),
    ("GRANULES",    "Granules India Ltd",               "Healthcare",        "Pharmaceuticals",             "INE101D01020", "NSE", "GRANUL",  1),
    ("AUROPHARMA",  "Aurobindo Pharma Ltd",             "Healthcare",        "Pharmaceuticals",             "INE406A01037", "NSE", "AUROPHA", 1),
    ("LUPIN",       "Lupin Ltd",                        "Healthcare",        "Pharmaceuticals",             "INE326A01037", "NSE", "LUPIN",   1),
    ("TORNTPHARM",  "Torrent Pharmaceuticals Ltd",     "Healthcare",        "Pharmaceuticals",             "INE685A01028", "NSE", "TORNTM",  1),

    # ── Energy ─────────────────────────────────────────────────────────────────
    ("ONGC",        "Oil and Natural Gas Corporation", "Energy",            "Oil Gas & Consumable Fuels",  "INE213A01029", "NSE", "ONGC",    1),
    ("IOC",         "Indian Oil Corporation Ltd",      "Energy",            "Oil Gas & Consumable Fuels",  "INE242A01010", "NSE", "IOC",     1),
    ("BPCL",        "Bharat Petroleum Corporation",    "Energy",            "Oil Gas & Consumable Fuels",  "INE029A01011", "NSE", "BPCL",    1),
    ("HINDPETRO",   "Hindustan Petroleum Corporation", "Energy",            "Oil Gas & Consumable Fuels",  "INE094A01015", "NSE", "HINDPET", 1),
    ("GAIL",        "GAIL (India) Ltd",                "Energy",            "Oil Gas & Consumable Fuels",  "INE129A01019", "NSE", "GAIL",    1),
    ("PETRONET",    "Petronet LNG Ltd",                "Energy",            "Oil Gas & Consumable Fuels",  "INE347G01014", "NSE", "PETROLN", 1),
    ("COALINDIA",   "Coal India Ltd",                  "Energy",            "Coal & Consumable Fuels",     "INE522F01014", "NSE", "COALIN",  1),
    ("NMDC",        "NMDC Ltd",                        "Materials",         "Steel",                       "INE584A01023", "NSE", "NMDC",    1),

    # ── Industrials ────────────────────────────────────────────────────────────
    ("LT",          "Larsen & Toubro Ltd",              "Industrials",       "Construction & Engineering",  "INE018A01030", "NSE", "LT",      1),
    ("SIEMENS",     "Siemens Ltd",                      "Industrials",       "Industrial Conglomerates",    "INE003A01024", "NSE", "SIEMEN",  1),
    ("ABB",         "ABB India Ltd",                    "Industrials",       "Electrical Equipment",        "INE117A01022", "NSE", "ABB",     1),
    ("CUMMINSIND",  "Cummins India Ltd",                "Industrials",       "Industrial Machinery",        "INE298A01020", "NSE", "CUMIND",  1),
    ("BHEL",        "Bharat Heavy Electricals Ltd",     "Industrials",       "Industrial Machinery",        "INE257A01026", "NSE", "BHEL",    1),
    ("HAL",         "Hindustan Aeronautics Ltd",        "Industrials",       "Aerospace & Defense",         "INE066F01020", "NSE", "HAL",     1),
    ("BEL",         "Bharat Electronics Ltd",           "Industrials",       "Aerospace & Defense",         "INE263A01024", "NSE", "BEL",     1),
    ("CONCOR",      "Container Corp of India Ltd",      "Industrials",       "Air Freight & Logistics",     "INE111A01025", "NSE", "CONCOR",  1),
    ("ADANIPORTS",  "Adani Ports and SEZ Ltd",          "Industrials",       "Transportation Infrastructure","INE742F01042","NSE", "ADNPRT",  1),
    ("ADANIENT",    "Adani Enterprises Ltd",            "Industrials",       "Industrial Conglomerates",    "INE423A01024", "NSE", "ADNENT",  1),
    ("IRCTC",       "Indian Railway Catering & Tourism","Industrials",       "Transportation Infrastructure","INE335Y01020","NSE", "IRCTC",   1),
    ("IRFC",        "Indian Railway Finance Corp",      "Financial Services","Diversified Financials",      "INE053F01010", "NSE", "IRFC",    1),

    # ── Materials ─────────────────────────────────────────────────────────────
    ("TATASTEEL",   "Tata Steel Ltd",                   "Materials",         "Steel",                       "INE081A01020", "NSE", "TATAST",  1),
    ("JSWSTEEL",    "JSW Steel Ltd",                    "Materials",         "Steel",                       "INE019A01038", "NSE", "JSWSTL",  1),
    ("HINDALCO",    "Hindalco Industries Ltd",          "Materials",         "Aluminium",                   "INE038A01020", "NSE", "HINDAL",  1),
    ("VEDL",        "Vedanta Ltd",                      "Materials",         "Diversified Metals & Mining", "INE205A01025", "NSE", "VEDANT",  1),
    ("NATIONALUM",  "National Aluminium Co Ltd",        "Materials",         "Aluminium",                   "INE139A01034", "NSE", "NATLAL",  1),
    ("JINDALSTEL",  "Jindal Steel and Power Ltd",       "Materials",         "Steel",                       "INE749A01030", "NSE", "JINSTE",  1),
    ("SAIL",        "Steel Authority of India Ltd",     "Materials",         "Steel",                       "INE114A01011", "NSE", "SAIL",    1),
    ("ULTRACEMCO",  "UltraTech Cement Ltd",             "Materials",         "Construction Materials",      "INE481G01011", "NSE", "ULTRAC",  1),
    ("AMBUJACEM",   "Ambuja Cements Ltd",               "Materials",         "Construction Materials",      "INE079A01024", "NSE", "AMBUJA",  1),
    ("ACC",         "ACC Ltd",                          "Materials",         "Construction Materials",      "INE012A01025", "NSE", "ACC",     1),
    ("RAMCOCEM",    "The Ramco Cements Ltd",            "Materials",         "Construction Materials",      "INE331A01037", "NSE", "RAMCEM",  1),
    ("PIDILITIND",  "Pidilite Industries Ltd",          "Materials",         "Specialty Chemicals",         "INE318A01026", "NSE", "PIDLIT",  1),
    ("SRF",         "SRF Ltd",                          "Materials",         "Specialty Chemicals",         "INE647A01010", "NSE", "SRF",     1),
    ("DEEPAKNTR",   "Deepak Nitrite Ltd",               "Materials",         "Specialty Chemicals",         "INE288B01029", "NSE", "DEEPNIT", 1),
    ("NAVINFLUOR",  "Navin Fluorine International",     "Materials",         "Specialty Chemicals",         "INE048G01026", "NSE", "NAVFLR",  1),
    ("AAPL",        "APL Apollo Tubes Ltd",             "Materials",         "Steel",                       "INE702C01019", "NSE", "APLAPOL", 1),

    # ── Consumer Discretionary ─────────────────────────────────────────────────
    ("TITAN",       "Titan Company Ltd",                "Consumer Discretionary","Luxury Goods",            "INE280A01028", "NSE", "TITAN",   1),
    ("MARUTI",      "Maruti Suzuki India Ltd",          "Consumer Discretionary","Automobiles",             "INE585B01010", "NSE", "MARUTI",  1),
    ("TATAMOTORS",  "Tata Motors Ltd",                  "Consumer Discretionary","Automobiles",             "INE155L01022", "NSE", "TATAMO",  1),
    ("M&M",         "Mahindra & Mahindra Ltd",          "Consumer Discretionary","Automobiles",             "INE101A01026", "NSE", "MAHIND",  1),
    ("BAJAJ-AUTO",  "Bajaj Auto Ltd",                   "Consumer Discretionary","Motorcycles",             "INE917I01010", "NSE", "BJJAUTO", 1),
    ("EICHERMOT",   "Eicher Motors Ltd",                "Consumer Discretionary","Motorcycles",             "INE066A01021", "NSE", "EICHMO",  1),
    ("HEROMOTOCO",  "Hero MotoCorp Ltd",                "Consumer Discretionary","Motorcycles",             "INE158A01026", "NSE", "HEROMO",  1),
    ("TVSMOTOR",    "TVS Motor Company Ltd",            "Consumer Discretionary","Motorcycles",             "INE494B01023", "NSE", "TVSMOT",  1),
    ("BOSCHLTD",    "Bosch Ltd",                        "Consumer Discretionary","Auto Components",         "INE323A01026", "NSE", "BOSCH",   1),
    ("BALKRISIND",  "Balkrishna Industries Ltd",        "Consumer Discretionary","Auto Components",         "INE787D01026", "NSE", "BALIND",  1),
    ("MHKIAJBL",    "Mahindra & Mahindra Financial",   "Financial Services",    "Consumer Finance",        "INE774D01024", "NSE", "MAHFIN",  1),
    ("PAGEIND",     "Page Industries Ltd",              "Consumer Discretionary","Apparel",                 "INE761H01022", "NSE", "PAGEIND", 1),
    ("TRENT",       "Trent Ltd",                        "Consumer Discretionary","Retail",                  "INE849A01020", "NSE", "TRENT",   1),
    ("SHOPERSTOP",  "Shoppers Stop Ltd",                "Consumer Discretionary","Retail",                  "INE498B01024", "NSE", "SHOPST",  1),
    ("DMART",       "Avenue Supermarts Ltd",            "Consumer Discretionary","Food Retail",             "INE192R01011", "NSE", "AVESUP",  1),

    # ── Utilities ─────────────────────────────────────────────────────────────
    ("NTPC",        "NTPC Ltd",                         "Utilities",         "Electric Utilities",          "INE733E01010", "NSE", "NTPC",    1),
    ("POWERGRID",   "Power Grid Corporation",           "Utilities",         "Electric Utilities",          "INE752E01010", "NSE", "PWRGRD",  1),
    ("TATAPOWER",   "Tata Power Company Ltd",           "Utilities",         "Electric Utilities",          "INE245A01021", "NSE", "TATAPW",  1),
    ("ADANIGREEN",  "Adani Green Energy Ltd",           "Utilities",         "Renewable Electricity",       "INE364U01010", "NSE", "ADNGRN",  1),
    ("ADANIPOWER",  "Adani Power Ltd",                  "Utilities",         "Electric Utilities",          "INE814H01011", "NSE", "ADNPWR",  1),
    ("TORNTPOWER",  "Torrent Power Ltd",                "Utilities",         "Electric Utilities",          "INE813H01021", "NSE", "TORNTPW", 1),
    ("CESC",        "CESC Ltd",                         "Utilities",         "Electric Utilities",          "INE486A01021", "NSE", "CESC",    1),
    ("IEX",         "Indian Energy Exchange Ltd",       "Utilities",         "Electric Utilities",          "INE022Q01020", "NSE", "IEX",     1),

    # ── Communication Services ─────────────────────────────────────────────────
    ("BHARTIARTL",  "Bharti Airtel Ltd",                "Communication Services","Wireless Telecom",        "INE397D01024", "NSE", "BHRTEL",  1),
    ("INDUSTOWER",  "Indus Towers Ltd",                 "Communication Services","Wireless Telecom",        "INE121J01017", "NSE", "INDTWRS", 1),
    ("IDEA",        "Vodafone Idea Ltd",                "Communication Services","Wireless Telecom",        "INE669E01016", "NSE", "IDEA",    1),
    ("MTNL",        "Mahanagar Telephone Nigam",        "Communication Services","Integrated Telecom",      "INE153A01019", "NSE", "MTNL",    1),
    ("TATACOMM",    "Tata Communications Ltd",          "Communication Services","Integrated Telecom",      "INE151B01027", "NSE", "TATACO",  1),

    # ── Real Estate ────────────────────────────────────────────────────────────
    ("DLF",         "DLF Ltd",                          "Real Estate",       "Real Estate Management",      "INE271C01023", "NSE", "DLF",     1),
    ("GODREJPROP",  "Godrej Properties Ltd",            "Real Estate",       "Real Estate Management",      "INE484J01027", "NSE", "GODPRO",  1),
    ("OBEROIRLTY",  "Oberoi Realty Ltd",                "Real Estate",       "Real Estate Management",      "INE093I01010", "NSE", "OBRIRL",  1),
    ("PHOENIXLTD",  "Phoenix Mills Ltd",                "Real Estate",       "Real Estate Management",      "INE211B01039", "NSE", "PHMILL",  1),
    ("PRESTIGE",    "Prestige Estates Projects Ltd",    "Real Estate",       "Real Estate Management",      "INE811K01011", "NSE", "PRESEST", 1),
    ("BRIGADE",     "Brigade Enterprises Ltd",          "Real Estate",       "Real Estate Management",      "INE791I01019", "NSE", "BRIGDE",  1),

    # ── Consumer Staples ──────────────────────────────────────────────────────
    ("HINDUNILVR",  "Hindustan Unilever Ltd",           "Consumer Staples",  "Household Products",          "INE030A01027", "NSE", "HINDUN",  1),
    ("ITC",         "ITC Ltd",                          "Consumer Staples",  "Tobacco",                     "INE154A01025", "NSE", "ITC",     1),
    ("PGHH",        "Procter & Gamble Hygiene",         "Consumer Staples",  "Household Products",          "INE179A01014", "NSE", "PGHH",    1),
]


def main() -> None:
    existing = pd.read_csv(UNIVERSE_PATH)
    existing_symbols = set(existing["symbol"])

    new_rows = []
    for row in ADDITIONAL_SYMBOLS:
        sym = row[0]
        if sym not in existing_symbols:
            new_rows.append({
                "symbol": row[0],
                "company_name": row[1],
                "sector": row[2],
                "industry": row[3],
                "isin": row[4],
                "exchange": row[5],
                "breeze_code": row[6],
                "lot_size": row[7],
            })

    if not new_rows:
        print("No new symbols to add.")
        return

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined.drop_duplicates(subset=["symbol"], keep="first", inplace=True)
    combined.sort_values("symbol", inplace=True)
    combined.reset_index(drop=True, inplace=True)
    combined.to_csv(UNIVERSE_PATH, index=False)

    print(f"Universe expanded: {len(existing)} -> {len(combined)} symbols")
    print(f"Added {len(new_rows)} new symbols")
    print("\nSector distribution:")
    print(combined["sector"].value_counts().to_string())


if __name__ == "__main__":
    main()
