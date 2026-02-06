"""Trading constants and enums."""

from dataclasses import dataclass
from enum import StrEnum


class AccountStatus(StrEnum):
    """Alpaca account status.

    Per Alpaca documentation:
    - ONBOARDING: Account application in progress
    - SUBMISSION_FAILED: Account application submission failed
    - SUBMITTED: Account application submitted and pending approval
    - ACCOUNT_UPDATED: Account information updated, resubmitted for approval
    - APPROVAL_PENDING: Initial approval received, pending final approval
    - ACTIVE: Account approved and active for trading
    - REJECTED: Account application rejected
    """

    ONBOARDING = "ONBOARDING"
    SUBMISSION_FAILED = "SUBMISSION_FAILED"
    SUBMITTED = "SUBMITTED"
    ACCOUNT_UPDATED = "ACCOUNT_UPDATED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"


class AccountActivityType(StrEnum):
    """Alpaca account activity types for non-trade activities.

    Per Alpaca Activities API documentation:
    - FILL: Order fills (handled separately in trades table)
    - TRANS: Cash transfers
    - MISC: Miscellaneous
    - ACATC: ACATS IN/OUT (Cash)
    - ACATS: ACATS IN/OUT (Securities)
    - CSD: Cash disbursement
    - CSR: Cash receipt
    - DIV: Dividends
    - DIVCGL: Dividend (capital gain long term)
    - DIVCGS: Dividend (capital gain short term)
    - DIVFEE: Dividend fee
    - DIVFT: Dividend (foreign tax withheld)
    - DIVNRA: Dividend (NRA withheld)
    - DIVROC: Dividend return of capital
    - DIVTW: Dividend (tax withheld)
    - DIVTXEX: Dividend (tax exempt)
    - INT: Interest
    - INTNRA: Interest (NRA withheld)
    - INTTW: Interest (tax withheld)
    - JNL: Journal entry
    - JNLC: Journal entry (cash)
    - JNLS: Journal entry (stock)
    - MA: Merger/acquisition
    - NC: Name change
    - OPASN: Option assignment
    - OPEXP: Option expiration
    - OPXRC: Option exercise
    - PTC: Pass thru charge
    - PTR: Pass thru rebate
    - REORG: Reorg CA
    - SC: Symbol change
    - SSO: Stock spinoff
    - SSP: Stock split
    - FEE: Regulatory fees
    - CFEE: Clearing fees
    """

    FILL = "FILL"
    TRANS = "TRANS"
    MISC = "MISC"
    ACATC = "ACATC"
    ACATS = "ACATS"
    CSD = "CSD"
    CSR = "CSR"
    DIV = "DIV"
    DIVCGL = "DIVCGL"
    DIVCGS = "DIVCGS"
    DIVFEE = "DIVFEE"
    DIVFT = "DIVFT"
    DIVNRA = "DIVNRA"
    DIVROC = "DIVROC"
    DIVTW = "DIVTW"
    DIVTXEX = "DIVTXEX"
    INT = "INT"
    INTNRA = "INTNRA"
    INTTW = "INTTW"
    JNL = "JNL"
    JNLC = "JNLC"
    JNLS = "JNLS"
    MA = "MA"
    NC = "NC"
    OPASN = "OPASN"
    OPEXP = "OPEXP"
    OPXRC = "OPXRC"
    PTC = "PTC"
    PTR = "PTR"
    REORG = "REORG"
    SC = "SC"
    SSO = "SSO"
    SSP = "SSP"
    FEE = "FEE"
    CFEE = "CFEE"


class OrderType(StrEnum):
    """Order type per Alpaca API."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderClass(StrEnum):
    """Order class per Alpaca API.

    - simple: Standard single-leg order
    - bracket: Entry with take-profit and stop-loss attached
    - oco: One-Cancels-Other (two orders, one cancels the other when filled)
    - oto: One-Triggers-Other (primary order triggers secondary when filled)
    """

    SIMPLE = "simple"
    BRACKET = "bracket"
    OCO = "oco"
    OTO = "oto"


class StrategyType(StrEnum):
    """Trading strategy types."""

    ORB = "orb"
    VWAP_REVERSION = "vwap_reversion"
    MOMENTUM_SCALP = "momentum_scalp"
    GAP_AND_GO = "gap_and_go"
    EOD_REVERSAL = "eod_reversal"
    EXPERIMENTAL = "experimental"


class OrderSide(StrEnum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    """Order status from broker."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TradeStatus(StrEnum):
    """Internal trade status."""

    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class DecisionType(StrEnum):
    """Trade decision type."""

    ENTRY = "entry"
    EXIT = "exit"
    HOLD = "hold"


class MarketRegime(StrEnum):
    """Market regime classification."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TradingSession(StrEnum):
    """Trading session types for 24/5 trading.

    Per Alpaca 24/5 trading:
    - Overnight: 8:00 PM to 4:00 AM ET
    - Pre-market: 4:00 AM to 9:30 AM ET
    - Regular: 9:30 AM to 4:00 PM ET
    - After-hours: 4:00 PM to 8:00 PM ET
    """

    OVERNIGHT = "overnight"
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"


@dataclass(frozen=True)
class TradingConstants:
    """Trading constants and limits."""

    # Asset Tiers
    TIER_1_ASSETS: tuple[str, ...] = ("SPY", "QQQ", "IWM")
    TIER_2_ASSETS: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META")

    # Full S&P 500 Components + Major ETFs for paper trading experimentation
    # Organized by sector (GICS classification)
    SP500_ASSETS: tuple[str, ...] = (
        # Major Index ETFs
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        # Information Technology (76 stocks)
        "AAPL",
        "MSFT",
        "NVDA",
        "AVGO",
        "ADBE",
        "CRM",
        "CSCO",
        "ACN",
        "IBM",
        "ORCL",
        "QCOM",
        "TXN",
        "NOW",
        "INTU",
        "AMD",
        "AMAT",
        "ADI",
        "LRCX",
        "MU",
        "KLAC",
        "SNPS",
        "CDNS",
        "MRVL",
        "FTNT",
        "PANW",
        "MSI",
        "APH",
        "TEL",
        "NXPI",
        "MPWR",
        "KEYS",
        "ON",
        "ANSS",
        "HPQ",
        "HPE",
        "CTSH",
        "IT",
        "GLW",
        "ZBRA",
        "TYL",
        "EPAM",
        "PTC",
        "AKAM",
        "JNPR",
        "FFIV",
        "SWKS",
        "QRVO",
        "TER",
        "ENPH",
        "SEDG",
        "FSLR",
        "GEN",
        "NTAP",
        "WDC",
        "STX",
        "TRMB",
        # Communication Services (25 stocks)
        "GOOGL",
        "GOOG",
        "META",
        "NFLX",
        "DIS",
        "CMCSA",
        "VZ",
        "T",
        "TMUS",
        "CHTR",
        "EA",
        "TTWO",
        "WBD",
        "OMC",
        "IPG",
        "PARA",
        "FOX",
        "FOXA",
        "NWS",
        "NWSA",
        "LYV",
        "MTCH",
        "DISH",
        # Consumer Discretionary (59 stocks)
        "AMZN",
        "TSLA",
        "HD",
        "MCD",
        "NKE",
        "LOW",
        "SBUX",
        "TJX",
        "BKNG",
        "CMG",
        "ORLY",
        "AZO",
        "ROST",
        "DHI",
        "LEN",
        "GM",
        "F",
        "MAR",
        "HLT",
        "YUM",
        "EBAY",
        "ETSY",
        "DPZ",
        "DARDEN",
        "WYNN",
        "LVS",
        "MGM",
        "CZR",
        "RCL",
        "CCL",
        "NCLH",
        "EXPE",
        "ABNB",
        "ULTA",
        "BBY",
        "DG",
        "DLTR",
        "KMX",
        "AAP",
        "GPC",
        "PHM",
        "NVR",
        "TOL",
        "MTH",
        "GRMN",
        "POOL",
        "TSCO",
        "WSM",
        "RH",
        "DECK",
        "LULU",
        "NIO",
        "RIVN",
        "LCID",
        "VFC",
        "HAS",
        "RL",
        "PVH",
        "TPR",
        # Consumer Staples (38 stocks)
        "PG",
        "KO",
        "PEP",
        "COST",
        "WMT",
        "PM",
        "MO",
        "MDLZ",
        "CL",
        "KMB",
        "GIS",
        "K",
        "HSY",
        "SJM",
        "EL",
        "STZ",
        "KHC",
        "KDP",
        "MNST",
        "ADM",
        "BG",
        "CAG",
        "CPB",
        "HRL",
        "MKC",
        "SYY",
        "TSN",
        "KR",
        "WBA",
        "TGT",
        "CHD",
        "CLX",
        "CLORX",
        "LW",
        "TAP",
        "BF.B",
        "SAM",
        # Health Care (64 stocks)
        "UNH",
        "JNJ",
        "LLY",
        "PFE",
        "ABBV",
        "MRK",
        "TMO",
        "ABT",
        "DHR",
        "BMY",
        "AMGN",
        "GILD",
        "VRTX",
        "REGN",
        "ISRG",
        "MDT",
        "SYK",
        "BDX",
        "ZTS",
        "CI",
        "ELV",
        "HUM",
        "CVS",
        "MCK",
        "CAH",
        "BSX",
        "EW",
        "DXCM",
        "IDXX",
        "IQV",
        "MTD",
        "A",
        "WAT",
        "HOLX",
        "ALGN",
        "COO",
        "TECH",
        "BIO",
        "RVTY",
        "CRL",
        "WST",
        "DGX",
        "LH",
        "PKI",
        "HSIC",
        "XRAY",
        "MOH",
        "CNC",
        "BIIB",
        "MRNA",
        "VTRS",
        "OGN",
        "CTLT",
        "INCY",
        "ILMN",
        "SGEN",
        "ALNY",
        "BMRN",
        "EXAS",
        "HCA",
        "UHS",
        "THC",
        "DVA",
        # Financials (74 stocks)
        "JPM",
        "V",
        "MA",
        "BAC",
        "WFC",
        "GS",
        "MS",
        "AXP",
        "BLK",
        "SCHW",
        "C",
        "USB",
        "PNC",
        "TFC",
        "COF",
        "BK",
        "AIG",
        "MET",
        "PRU",
        "ALL",
        "CB",
        "MMC",
        "AON",
        "ICE",
        "CME",
        "SPGI",
        "MCO",
        "MSCI",
        "AFL",
        "TRV",
        "PGR",
        "HIG",
        "CINF",
        "L",
        "GL",
        "AIZ",
        "AJG",
        "BRO",
        "WTW",
        "RJF",
        "NTRS",
        "STT",
        "FITB",
        "HBAN",
        "CFG",
        "KEY",
        "RF",
        "ZION",
        "FRC",
        "SBNY",
        "MTB",
        "CMA",
        "ALLY",
        "SYF",
        "DFS",
        "NDAQ",
        "CBOE",
        "TROW",
        "IVZ",
        "BEN",
        "AMG",
        "FDS",
        "MKTX",
        "VOYA",
        "LNC",
        "UNM",
        "PFG",
        "RE",
        "AMP",
        "EFX",
        "FIS",
        "FISV",
        "GPN",
        "PYPL",
        # Industrials (77 stocks)
        "CAT",
        "DE",
        "UNP",
        "UPS",
        "HON",
        "RTX",
        "BA",
        "GE",
        "LMT",
        "MMM",
        "EMR",
        "ETN",
        "ITW",
        "PH",
        "ROK",
        "CMI",
        "PCAR",
        "NSC",
        "CSX",
        "FDX",
        "WM",
        "RSG",
        "FAST",
        "CTAS",
        "PAYX",
        "VRSK",
        "GD",
        "NOC",
        "LHX",
        "TDG",
        "HWM",
        "TXT",
        "HII",
        "CW",
        "LDOS",
        "J",
        "BAH",
        "AXON",
        "CARR",
        "OTIS",
        "DOV",
        "AME",
        "ROP",
        "IEX",
        "XYL",
        "GWW",
        "SWK",
        "SNA",
        "IR",
        "PNR",
        "AOS",
        "LII",
        "TT",
        "GNRC",
        "ALLE",
        "MAS",
        "JCI",
        "TRANE",
        "PWR",
        "HUBB",
        "FTV",
        "NDSN",
        "WAB",
        "GGG",
        "RBC",
        "URI",
        "DAL",
        "UAL",
        "LUV",
        "AAL",
        "ALK",
        "JBHT",
        "EXPD",
        "CHRW",
        "ODFL",
        "XPO",
        "LSTR",
        # Energy (23 stocks)
        "XOM",
        "CVX",
        "COP",
        "SLB",
        "EOG",
        "MPC",
        "PSX",
        "VLO",
        "OXY",
        "PXD",
        "DVN",
        "HAL",
        "BKR",
        "FANG",
        "HES",
        "KMI",
        "WMB",
        "OKE",
        "TRGP",
        "LNG",
        "APA",
        "CTRA",
        "MRO",
        # Materials (28 stocks)
        "LIN",
        "APD",
        "SHW",
        "ECL",
        "FCX",
        "NEM",
        "NUE",
        "DD",
        "DOW",
        "PPG",
        "VMC",
        "MLM",
        "ALB",
        "CF",
        "MOS",
        "CTVA",
        "FMC",
        "IFF",
        "CE",
        "EMN",
        "AVY",
        "SEE",
        "PKG",
        "IP",
        "WRK",
        "BALL",
        "AMCR",
        "BLL",
        # Utilities (30 stocks)
        "NEE",
        "DUK",
        "SO",
        "D",
        "AEP",
        "EXC",
        "SRE",
        "XEL",
        "PEG",
        "ED",
        "WEC",
        "ES",
        "AWK",
        "AEE",
        "DTE",
        "ETR",
        "FE",
        "PPL",
        "CMS",
        "CNP",
        "EVRG",
        "AES",
        "ATO",
        "NI",
        "LNT",
        "PNW",
        "NRG",
        "CEG",
        "VST",
        "PCG",
        # Real Estate (31 stocks)
        "PLD",
        "AMT",
        "EQIX",
        "CCI",
        "PSA",
        "O",
        "WELL",
        "DLR",
        "SPG",
        "AVB",
        "EQR",
        "VTR",
        "ARE",
        "MAA",
        "UDR",
        "ESS",
        "CPT",
        "PEAK",
        "HST",
        "KIM",
        "REG",
        "FRT",
        "BXP",
        "VNO",
        "SLG",
        "HIW",
        "CBRE",
        "JLL",
        "CSGP",
        "IRM",
        "EXR",
    )

    # Minimum requirements
    MIN_STOCK_PRICE: float = 5.0
    MIN_DAILY_VOLUME: int = 5_000_000
    MAX_BID_ASK_SPREAD_PCT: float = 0.1

    # Strategy-specific position sizes (% of capital)
    ORB_POSITION_SIZE_PCT: float = 10.0
    VWAP_POSITION_SIZE_PCT: float = 8.0
    MOMENTUM_POSITION_SIZE_PCT: float = 5.0
    GAP_POSITION_SIZE_PCT: float = 15.0
    EOD_POSITION_SIZE_PCT: float = 10.0

    # Strategy-specific max concurrent positions
    ORB_MAX_POSITIONS: int = 3
    VWAP_MAX_POSITIONS: int = 4
    MOMENTUM_MAX_POSITIONS: int = 5
    GAP_MAX_POSITIONS: int = 2
    EOD_MAX_POSITIONS: int = 2

    # Auto-disable thresholds
    MAX_CONSECUTIVE_LOSSES: int = 5
    MIN_WIN_RATE_THRESHOLD: float = 0.40
    MIN_PROFIT_FACTOR: float = 0.8
    MIN_TRADES_FOR_EVALUATION: int = 20

    # Circuit breaker cooldowns (in seconds)
    STRATEGY_PAUSE_DURATION: int = 86400  # 1 day
    DAILY_LOSS_COOLDOWN: int = 0  # Until next trading day

    # Time constants
    MARKET_TIMEZONE: str = "America/New_York"
    PRE_MARKET_START_HOUR: int = 4
    AFTER_HOURS_END_HOUR: int = 20

    # 24/5 Trading Session Times (ET)
    # Overnight: 8:00 PM to 4:00 AM ET
    OVERNIGHT_START_HOUR: int = 20  # 8:00 PM
    OVERNIGHT_END_HOUR: int = 4  # 4:00 AM
    # Pre-market: 4:00 AM to 9:30 AM ET
    PRE_MARKET_END_HOUR: int = 9
    PRE_MARKET_END_MINUTE: int = 30
    # Regular: 9:30 AM to 4:00 PM ET
    REGULAR_START_HOUR: int = 9
    REGULAR_START_MINUTE: int = 30
    REGULAR_END_HOUR: int = 16
    # After-hours: 4:00 PM to 8:00 PM ET
    AFTER_HOURS_START_HOUR: int = 16
    # AFTER_HOURS_END_HOUR already defined above (20)

    # ORB Strategy
    ORB_RANGE_MINUTES: int = 15
    ORB_BREAKOUT_THRESHOLD_PCT: float = 0.1
    ORB_STOP_LOSS_PCT: float = 1.0
    ORB_TAKE_PROFIT_PCT: float = 2.0

    # VWAP Strategy
    # Paper trading: relaxed from 1.5/30/70 to generate more signals for data collection
    VWAP_DEVIATION_THRESHOLD_PCT: float = 1.0
    VWAP_RSI_OVERSOLD: float = 35.0
    VWAP_RSI_OVERBOUGHT: float = 65.0
    VWAP_TARGET_PCT: float = 0.2
    VWAP_STOP_LOSS_PCT: float = 0.8
    VWAP_MAX_HOLD_MINUTES: int = 60

    # Momentum Strategy
    MOMENTUM_VOLUME_RATIO: float = 1.5
    # Paper trading: widened from 40/60 to catch more crossovers
    MOMENTUM_RSI_MIN: float = 35.0
    MOMENTUM_RSI_MAX: float = 65.0
    MOMENTUM_TAKE_PROFIT_PCT: float = 1.5
    MOMENTUM_STOP_LOSS_PCT: float = 0.6

    # Gap & Go Strategy
    # Paper trading: relaxed from 3.0%/200k to find more gap candidates
    GAP_MIN_PCT: float = 1.5
    GAP_ENTRY_DELAY_MINUTES: int = 5
    GAP_PULLBACK_PCT: float = 0.5
    GAP_MIN_PREMARKET_VOLUME: int = 50_000
    GAP_STOP_LOSS_PCT: float = 2.0
    GAP_MAX_PROFIT_PCT: float = 5.0
    GAP_EXIT_TIME_HOUR: int = 10
    GAP_EXIT_TIME_MINUTE: int = 30

    # EOD Reversal Strategy
    EOD_START_HOUR: int = 15
    # Paper trading: relaxed from 25/75/2.0 to generate signals during the short EOD window
    EOD_RSI_OVERSOLD: float = 30.0
    EOD_RSI_OVERBOUGHT: float = 70.0
    EOD_VWAP_DEVIATION_PCT: float = 1.5
    EOD_STOP_LOSS_PCT: float = 1.0
    EOD_TAKE_PROFIT_PCT: float = 1.5
    EOD_EXIT_MINUTE: int = 55  # Exit at 3:55 PM

    # Dynamic Symbol Scanner defaults
    SCANNER_MIN_PRICE: float = 5.0
    SCANNER_MIN_AVG_VOLUME: int = 1_000_000
    SCANNER_LOOKBACK_DAYS: int = 5
    SCANNER_MAX_SYMBOLS: int = 1000
