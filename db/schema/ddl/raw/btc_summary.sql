--DROP TABLE IF EXISTS btc_summary;

CREATE TABLE IF NOT EXISTS btc_summary
(
    -- summary of pm_window.py
    SLUG                         VARCHAR,  -- slug: btc-updown-5m-<window start unix>
    TITLE                        VARCHAR,           -- title (event)
    CONDITION_ID                 VARCHAR,  -- markets[0].conditionId
    UP_TOKEN_ID                  VARCHAR,           -- tokens['Up']: CLOB token id (clobTokenIds[0])
    DOWN_TOKEN_ID                VARCHAR,           -- tokens['Down']: CLOB token id (clobTokenIds[1])
    RESOLUTION_SOURCE            VARCHAR,           -- resolution_source (markets[0].resolutionSource)
    START                        TIMESTAMPTZ,       -- start: 5-minute window start (markets[0].eventStartTime)
    "END"                        TIMESTAMPTZ,       -- end: 5-minute window end (markets[0].endDate)
    TWAP_LOOKBACK_S              INTEGER,           -- twap_lookback_s (cryptoMarketConfig.twapLookbackSeconds)
    PRICE_TO_BEAT                DOUBLE,            -- price_to_beat: strike (eventMetadata.priceToBeat)
    FINAL_PRICE                  DOUBLE,            -- final_price (eventMetadata.finalPrice)
    MOVE_USD                     DOUBLE,            -- move_usd: FINAL_PRICE - PRICE_TO_BEAT
    WINNER                       VARCHAR,           -- Up / Down, 'unresolved' if not resolved
    VOLUME                       DOUBLE,            -- volume (markets[0].volume, a string in the API)
    N_TRADES                     INTEGER,           -- n_trades: rows in btc_trades

    -- market: parts of its nested objects
    RESULT                       VARCHAR,           -- Up / Down, NULL if not resolved
    UP_PRICE                     DOUBLE,            -- outcomePrices[0]: 1 if Up won
    DOWN_PRICE                   DOUBLE,            -- outcomePrices[1]: 1 if Down won
    FEE_RATE                     DOUBLE,            -- feeSchedule.rate
    FEE_EXPONENT                 DOUBLE,            -- feeSchedule.exponent
    FEE_TAKER_ONLY               BOOLEAN,           -- feeSchedule.takerOnly
    FEE_REBATE_RATE              DOUBLE,            -- feeSchedule.rebateRate
    CRYPTO_ASSET                 VARCHAR,           -- cryptoMarketConfig.asset
    CRYPTO_DURATION              VARCHAR,           -- cryptoMarketConfig.duration
    TWAP_ENABLED                 BOOLEAN,           -- cryptoMarketConfig.twapEnabled
    RAW_EVENT                    JSON,              -- the whole Gamma event object (markets[0] included), as returned

    -- market: fields (Gamma markets[0])
    MARKET_ID                    VARCHAR,           -- markets[0].id
    QUESTION                     VARCHAR,           -- markets[0].question
    QUESTION_ID                  VARCHAR,           -- markets[0].questionID
    DESCRIPTION                  VARCHAR,           -- markets[0].description
    IMAGE                        VARCHAR,           -- markets[0].image
    ICON                         VARCHAR,           -- markets[0].icon
    MARKET_MAKER_ADDRESS         VARCHAR,           -- markets[0].marketMakerAddress
    COMBO_STATUS                 VARCHAR,           -- markets[0].comboStatus
    GROUP_ITEM_THRESHOLD         DOUBLE,            -- markets[0].groupItemThreshold
    EVENT_START_TIME             TIMESTAMPTZ,       -- markets[0].eventStartTime
    END_DATE                     TIMESTAMPTZ,       -- markets[0].endDate
    START_DATE                   TIMESTAMPTZ,       -- markets[0].startDate
    END_DATE_ISO                 DATE,              -- markets[0].endDateIso
    START_DATE_ISO               DATE,              -- markets[0].startDateIso
    CREATED_AT                   TIMESTAMPTZ,       -- markets[0].createdAt
    UPDATED_AT                   TIMESTAMPTZ,       -- markets[0].updatedAt
    CLOSED_TIME                  TIMESTAMPTZ,       -- markets[0].closedTime
    UMA_END_DATE                 TIMESTAMPTZ,       -- markets[0].umaEndDate
    ACCEPTING_ORDERS_TIMESTAMP   TIMESTAMPTZ,       -- markets[0].acceptingOrdersTimestamp
    OUTCOMES                     VARCHAR,           -- markets[0].outcomes
    OUTCOME_PRICES               VARCHAR,           -- markets[0].outcomePrices
    CLOB_TOKEN_IDS               VARCHAR,           -- markets[0].clobTokenIds
    UMA_RESOLUTION_STATUS        VARCHAR,           -- markets[0].umaResolutionStatus
    UMA_RESOLUTION_STATUSES      VARCHAR,           -- markets[0].umaResolutionStatuses
    AUTOMATICALLY_RESOLVED       BOOLEAN,           -- markets[0].automaticallyResolved
    AUTOMATICALLY_ACTIVE         BOOLEAN,           -- markets[0].automaticallyActive
    MANUAL_ACTIVATION            BOOLEAN,           -- markets[0].manualActivation
    ACTIVE                       BOOLEAN,           -- markets[0].active
    CLOSED                       BOOLEAN,           -- markets[0].closed
    ARCHIVED                     BOOLEAN,           -- markets[0].archived
    NEW                          BOOLEAN,           -- markets[0].new
    FEATURED                     BOOLEAN,           -- markets[0].featured
    RESTRICTED                   BOOLEAN,           -- markets[0].restricted
    APPROVED                     BOOLEAN,           -- markets[0].approved
    READY                        BOOLEAN,           -- markets[0].ready
    FUNDED                       BOOLEAN,           -- markets[0].funded
    HAS_REVIEWED_DATES           BOOLEAN,           -- markets[0].hasReviewedDates
    ACCEPTING_ORDERS             BOOLEAN,           -- markets[0].acceptingOrders
    ENABLE_ORDER_BOOK            BOOLEAN,           -- markets[0].enableOrderBook
    CLEAR_BOOK_ON_START          BOOLEAN,           -- markets[0].clearBookOnStart
    PENDING_DEPLOYMENT           BOOLEAN,           -- markets[0].pendingDeployment
    DEPLOYING                    BOOLEAN,           -- markets[0].deploying
    CYOM                         BOOLEAN,           -- markets[0].cyom
    RFQ_ENABLED                  BOOLEAN,           -- markets[0].rfqEnabled
    PAGER_DUTY_NOTIFICATION_ENABLED BOOLEAN,        -- markets[0].pagerDutyNotificationEnabled
    SHOW_GMP_SERIES              BOOLEAN,           -- markets[0].showGmpSeries
    SHOW_GMP_OUTCOME             BOOLEAN,           -- markets[0].showGmpOutcome
    NEG_RISK                     BOOLEAN,           -- markets[0].negRisk
    NEG_RISK_OTHER               BOOLEAN,           -- markets[0].negRiskOther
    HOLDING_REWARDS_ENABLED      BOOLEAN,           -- markets[0].holdingRewardsEnabled
    VOLUME_NUM                   DOUBLE,            -- markets[0].volumeNum
    VOLUME_CLOB                  DOUBLE,            -- markets[0].volumeClob
    LIQUIDITY                    DOUBLE,            -- markets[0].liquidity
    LIQUIDITY_NUM                DOUBLE,            -- markets[0].liquidityNum
    LIQUIDITY_AMM                DOUBLE,            -- markets[0].liquidityAmm
    LIQUIDITY_CLOB               DOUBLE,            -- markets[0].liquidityClob
    COMPETITIVE                  DOUBLE,            -- markets[0].competitive
    LAST_TRADE_PRICE             DOUBLE,            -- markets[0].lastTradePrice
    BEST_BID                     DOUBLE,            -- markets[0].bestBid
    BEST_ASK                     DOUBLE,            -- markets[0].bestAsk
    SPREAD                       DOUBLE,            -- markets[0].spread
    ONE_HOUR_PRICE_CHANGE        DOUBLE,            -- markets[0].oneHourPriceChange
    ONE_DAY_PRICE_CHANGE         DOUBLE,            -- markets[0].oneDayPriceChange
    ORDER_PRICE_MIN_TICK_SIZE    DOUBLE,            -- markets[0].orderPriceMinTickSize
    ORDER_MIN_SIZE               DOUBLE,            -- markets[0].orderMinSize
    REWARDS_MIN_SIZE             DOUBLE,            -- markets[0].rewardsMinSize
    REWARDS_MAX_SPREAD           DOUBLE,            -- markets[0].rewardsMaxSpread
    FEES_ENABLED                 BOOLEAN,           -- markets[0].feesEnabled
    FEE_TYPE                     VARCHAR,           -- markets[0].feeType
    MAKER_BASE_FEE               INTEGER,           -- markets[0].makerBaseFee
    TAKER_BASE_FEE               INTEGER,           -- markets[0].takerBaseFee
    MAKER_REBATES_FEE_SHARE_BPS  INTEGER,           -- markets[0].makerRebatesFeeShareBps
    CRYPTO_MARKET_CONFIG_ID      VARCHAR,           -- markets[0].cryptoMarketConfigId
    VERSION                      VARCHAR,           -- markets[0].version

    -- event: fields (Gamma event; EVENT_ prefix)
    EVENT_ID                     VARCHAR,           -- event.id
    EVENT_TICKER                 VARCHAR,           -- event.ticker
    EVENT_SLUG                   VARCHAR,           -- event.slug
    EVENT_DESCRIPTION            VARCHAR,           -- event.description
    EVENT_RESOLUTION_SOURCE      VARCHAR,           -- event.resolutionSource
    EVENT_IMAGE                  VARCHAR,           -- event.image
    EVENT_ICON                   VARCHAR,           -- event.icon
    EVENT_SERIES_SLUG            VARCHAR,           -- event.seriesSlug
    EVENT_STARTTIME              TIMESTAMPTZ,       -- event.startTime
    EVENT_START_DATE             TIMESTAMPTZ,       -- event.startDate
    EVENT_CREATION_DATE          TIMESTAMPTZ,       -- event.creationDate
    EVENT_END_DATE               TIMESTAMPTZ,       -- event.endDate
    EVENT_CREATED_AT             TIMESTAMPTZ,       -- event.createdAt
    EVENT_UPDATED_AT             TIMESTAMPTZ,       -- event.updatedAt
    EVENT_CLOSED_TIME            TIMESTAMPTZ,       -- event.closedTime
    EVENT_ACTIVE                 BOOLEAN,           -- event.active
    EVENT_CLOSED                 BOOLEAN,           -- event.closed
    EVENT_ARCHIVED               BOOLEAN,           -- event.archived
    EVENT_NEW                    BOOLEAN,           -- event.new
    EVENT_FEATURED               BOOLEAN,           -- event.featured
    EVENT_RESTRICTED             BOOLEAN,           -- event.restricted
    EVENT_ENABLE_ORDER_BOOK      BOOLEAN,           -- event.enableOrderBook
    EVENT_AUTOMATICALLY_RESOLVED BOOLEAN,           -- event.automaticallyResolved
    EVENT_AUTOMATICALLY_ACTIVE   BOOLEAN,           -- event.automaticallyActive
    EVENT_CYOM                   BOOLEAN,           -- event.cyom
    EVENT_SHOW_ALL_OUTCOMES      BOOLEAN,           -- event.showAllOutcomes
    EVENT_SHOW_MARKET_IMAGES     BOOLEAN,           -- event.showMarketImages
    EVENT_NEG_RISK               BOOLEAN,           -- event.negRisk
    EVENT_ENABLE_NEG_RISK        BOOLEAN,           -- event.enableNegRisk
    EVENT_NEG_RISK_AUGMENTED     BOOLEAN,           -- event.negRiskAugmented
    EVENT_PENDING_DEPLOYMENT     BOOLEAN,           -- event.pendingDeployment
    EVENT_DEPLOYING              BOOLEAN,           -- event.deploying
    EVENT_VOLUME                 DOUBLE,            -- event.volume
    EVENT_LIQUIDITY              DOUBLE,            -- event.liquidity
    EVENT_LIQUIDITY_AMM          DOUBLE,            -- event.liquidityAmm
    EVENT_LIQUIDITY_CLOB         DOUBLE,            -- event.liquidityClob
    EVENT_OPEN_INTEREST          DOUBLE,            -- event.openInterest
    EVENT_COMPETITIVE            DOUBLE,            -- event.competitive
    EVENT_COMMENT_COUNT          INTEGER,           -- event.commentCount
    EVENT_SERIES                 JSON,              -- event.series
    EVENT_TAGS                   JSON,              -- event.tags
    EVENT_METADATA               JSON,              -- event.eventMetadata
    EVENT_VERSION                VARCHAR            -- event.version
);
