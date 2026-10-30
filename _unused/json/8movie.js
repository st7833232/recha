/*
 * WebHTV Shared CatVod JS Spider - 8Movie
 *
 * iOS + Android shared source.
 * IMPORTANT: no ES-module import/export syntax.
 *
 * Android network strategy:
 * - HTTP uses non-blocking Promise requests.
 * - Empty/failed responses retry up to 3 times.
 * - Retry backoff: 250ms, then 700ms.
 * - iOS keeps synchronous requests with a small bounded retry.
 */

var SITE = 'https://www.8movie.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';

var PAGE_TIMEOUT = 7000;
var SEARCH_TIMEOUT = 5000;


/* =========================================================
 * BASIC
 * ========================================================= */

function json(value) {
    try {
        return JSON.stringify(
            value === undefined || value === null
                ? {}
                : value
        );
    } catch (error) {
        return '{}';
    }
}

function clean(value) {
    return String(
        value === undefined || value === null
            ? ''
            : value
    )
        .replace(/&nbsp;/gi, ' ')
        .replace(/&amp;/gi, '&')
        .replace(/&quot;/gi, '"')
        .replace(/&#39;/gi, "'")
        .replace(/&#x27;/gi, "'")
        .replace(/\s+/g, ' ')
        .replace(/^\s+|\s+$/g, '');
}

function ensureRequestBridge() {
    if (
        typeof globalThis.req !== 'function' &&
        typeof http === 'function'
    ) {
        globalThis.req = http;
    }
}

function requestHeaders(referer) {
    return {
        'User-Agent': UA,
        'Referer': referer || SITE + '/',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        'Accept': '*/*'
    };
}

function requestPage(
    url,
    referer,
    timeout
) {
    ensureRequestBridge();

    var request =
        typeof req === 'function'
            ? req
            : globalThis.req;

    if (typeof request !== 'function') {
        return '';
    }

    var result =
        request(
            url,
            {
                method: 'GET',
                headers:
                    requestHeaders(
                        referer
                    ),
                timeout:
                    timeout ||
                    PAGE_TIMEOUT
            }
        ) || {};

    return (
        result.content ||
        result.body ||
        ''
    );
}


var RETRY_ATTEMPTS = 3;
var RETRY_DELAY_1 = 250;
var RETRY_DELAY_2 = 700;
var RETRY_TIMEOUT = 4000;

function responseBody(result) {
    if (!result) return '';
    return result.content || result.body || '';
}

function requestPageSyncRetry(url, referer, timeout, attempts) {
    var maxAttempts = attempts || RETRY_ATTEMPTS;
    var body = '';

    for (var i = 0; i < maxAttempts; i++) {
        try {
            body = requestPage(url, referer, timeout);
        } catch (error) {
            body = '';
        }

        if (body) return body;
    }

    return '';
}

function requestPageAsyncRetry(url, referer, timeout, attempts) {
    var maxAttempts = attempts || RETRY_ATTEMPTS;
    var requestTimeout = timeout || RETRY_TIMEOUT;

    if (!isAndroidRuntime() || typeof http !== 'function') {
        return Promise.resolve(
            requestPageSyncRetry(
                url,
                referer,
                requestTimeout,
                maxAttempts
            )
        );
    }

    return new Promise(function(resolve) {
        function run(attempt) {
            var promise;

            try {
                promise = http(
                    url,
                    {
                        method: 'GET',
                        headers: requestHeaders(referer),
                        timeout: requestTimeout
                    }
                );
            } catch (error) {
                promise = Promise.resolve(null);
            }

            Promise.resolve(promise)
                .then(function(result) {
                    var body = responseBody(result);

                    if (body || attempt >= maxAttempts) {
                        resolve(body || '');
                        return;
                    }

                    var delay =
                        attempt === 1
                            ? RETRY_DELAY_1
                            : RETRY_DELAY_2;

                    setTimeout(
                        function() {
                            run(attempt + 1);
                        },
                        delay
                    );
                })
                .catch(function() {
                    if (attempt >= maxAttempts) {
                        resolve('');
                        return;
                    }

                    var delay =
                        attempt === 1
                            ? RETRY_DELAY_1
                            : RETRY_DELAY_2;

                    setTimeout(
                        function() {
                            run(attempt + 1);
                        },
                        delay
                    );
                });
        }

        run(1);
    });
}


function originOf(url) {
    var match =
        /^(https?:\/\/[^/]+)/i.exec(
            String(
                url || ''
            )
        );

    return match ? match[1] : '';
}

function absolute(
    value,
    base
) {
    var url = clean(value);
    var root = base || SITE + '/';

    if (!url) return '';

    if (/^https?:\/\//i.test(url)) {
        return url;
    }

    if (url.indexOf('//') === 0) {
        return 'https:' + url;
    }

    if (url.charAt(0) === '/') {
        return originOf(root) + url;
    }

    return String(root).replace(/[^/]*$/, '') + url;
}



function isAndroidRuntime() {
    /*
     * Android QuickJS exposes the native _http() bridge before
     * this source is evaluated. iOS WebHTV does not expose _http.
     *
     * This lets one shared JS avoid Android startup network I/O
     * without changing the iOS behavior.
     */
    return (
        typeof globalThis._http === 'function' ||
        typeof _http === 'function'
    );
}

/* =========================================================
 * URL
 * ========================================================= */

function movieId(value) {
    var match =
        /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(
            String(
                value || ''
            )
        );

    return match ? match[1] : '';
}

function isCategoryId(id) {
    return /^(1|2|3|4|5|6)$/.test(
        String(
            id || ''
        )
    );
}

function playInfo(value) {
    var match =
        /\/play\/(\d+)\/(\d+)\/?(?:[?#].*)?$/i.exec(
            String(
                value || ''
            )
        );

    if (!match) {
        return null;
    }

    return {
        movie: match[1],
        episode: match[2],
        path:
            '/play/' +
            match[1] +
            '/' +
            match[2] +
            '/'
    };
}


/* =========================================================
 * LIST
 * ========================================================= */

function titleFromNode(node) {
    var title =
        clean(
            pdfh(
                node,
                'a&&title'
            ) ||
            pdfh(
                node,
                'img&&alt'
            ) ||
            pdfh(
                node,
                'a&&Text'
            ) ||
            pdfh(
                node,
                'Text'
            ) ||
            ''
        );

    return clean(
        title
            .replace(
                /^\s*\d+\s*集\s*/,
                ''
            )
            .replace(
                /^立即觀看\s*/i,
                ''
            )
    );
}

function parseMovieList(html) {
    var nodes =
        pdfa(
            html,
            'a[href*="/movies/"]'
        );

    var result = [];
    var seen = {};

    for (var i = 0; i < nodes.length; i++) {
        var href =
            pdfh(
                nodes[i],
                'a&&href'
            ) ||
            '';

        var id =
            movieId(
                href
            );

        if (!id) {
            continue;
        }

        if (isCategoryId(id)) {
            continue;
        }

        if (seen[id]) {
            continue;
        }

        var title =
            titleFromNode(
                nodes[i]
            );

        if (!title) {
            continue;
        }

        if (
            title === '分類' ||
            title === '最新' ||
            title === '排行' ||
            title === '標籤' ||
            title === '追劇' ||
            title === '會員' ||
            /^More$/i.test(title)
        ) {
            continue;
        }

        var text =
            clean(
                pdfh(
                    nodes[i],
                    'a&&Text'
                ) ||
                pdfh(
                    nodes[i],
                    'Text'
                ) ||
                ''
            );

        var episodeMatch =
            /(\d+)\s*集/.exec(
                text
            );

        result.push({
            vod_id: id,
            vod_name: title,
            vod_pic: '',
            vod_remarks:
                episodeMatch
                    ? episodeMatch[1] + '集'
                    : ''
        });

        seen[id] = true;
    }

    return result;
}


/* =========================================================
 * DETAIL
 * ========================================================= */

function metaContent(
    html,
    propertyName,
    nameValue
) {
    var value = '';

    if (propertyName) {
        value =
            pdfh(
                html,
                'meta[property="' +
                propertyName +
                '"]&&content'
            );
    }

    if (
        !value &&
        nameValue
    ) {
        value =
            pdfh(
                html,
                'meta[name="' +
                nameValue +
                '"]&&content'
            );
    }

    return clean(value);
}

function detailTitle(html) {
    var value =
        clean(
            pdfh(
                html,
                'h1&&Text'
            ) ||
            metaContent(
                html,
                'og:title',
                ''
            ) ||
            pdfh(
                html,
                'title&&Text'
            ) ||
            ''
        );

    return clean(
        value
            .replace(
                /\s*-\s*8movie\.com.*$/i,
                ''
            )
            .replace(
                /\s*-\s*八影短劇網.*$/i,
                ''
            )
            .replace(
                /\s*-\s*8Movie.*$/i,
                ''
            )
    );
}

function detailDescription(html) {
    var value =
        metaContent(
            html,
            'og:description',
            'description'
        );

    if (value) {
        return value;
    }

    var nodes =
        pdfa(
            html,
            'h6'
        );

    for (var i = 0; i < nodes.length; i++) {
        var text =
            clean(
                pdfh(
                    nodes[i],
                    'Text'
                ) ||
                ''
            );

        if (
            text.length > 20 &&
            text.indexOf(
                '溫馨提示'
            ) === -1
        ) {
            return text;
        }
    }

    return '';
}


/* =========================================================
 * EPISODES
 * ========================================================= */

function parseEpisodes(
    html,
    id
) {
    var nodes =
        pdfa(
            html,
            'a[href*="/play/"]'
        );

    var result = [];
    var seen = {};

    for (var i = 0; i < nodes.length; i++) {
        var href =
            pdfh(
                nodes[i],
                'a&&href'
            ) ||
            '';

        var info =
            playInfo(
                href
            );

        if (!info) {
            continue;
        }

        if (
            String(
                info.movie
            ) !==
            String(
                id
            )
        ) {
            continue;
        }

        var fullURL =
            absolute(
                info.path,
                SITE + '/'
            );

        if (
            !fullURL ||
            seen[fullURL]
        ) {
            continue;
        }

        var label =
            clean(
                pdfh(
                    nodes[i],
                    'a&&Text'
                ) ||
                pdfh(
                    nodes[i],
                    'Text'
                ) ||
                ''
            );

        if (!label) {
            var number =
                parseInt(
                    info.episode,
                    10
                );

            if (!number) {
                number =
                    result.length +
                    1;
            }

            label =
                '第' +
                number +
                '集';
        }

        result.push(
            label +
            '$' +
            fullURL
        );

        seen[fullURL] = true;
    }

    return result;
}


/* =========================================================
 * CATEGORY
 * ========================================================= */

function categoryURL(tid) {
    var value =
        String(
            tid || 'update'
        );

    if (value === 'update') {
        return SITE + '/movies/update/';
    }

    if (value === 'rank') {
        return SITE + '/movies/rank/';
    }

    if (/^[1-6]$/.test(value)) {
        return (
            SITE +
            '/movies/' +
            value +
            '/'
        );
    }

    return SITE + '/movies/update/';
}


/* =========================================================
 * SEARCH
 * ========================================================= */

function matchKeyword(
    list,
    keyword
) {
    var result = [];
    var key =
        clean(
            keyword
        )
            .toLowerCase();

    if (!key) {
        return result;
    }

    for (var i = 0; i < list.length; i++) {
        var name =
            String(
                list[i].vod_name ||
                ''
            )
                .toLowerCase();

        if (
            name.indexOf(
                key
            ) !== -1
        ) {
            result.push(
                list[i]
            );
        }
    }

    return result;
}

function appendUnique(
    target,
    items,
    seen
) {
    for (var i = 0; i < items.length; i++) {
        var id =
            String(
                items[i].vod_id ||
                ''
            );

        if (
            !id ||
            seen[id]
        ) {
            continue;
        }

        seen[id] = true;
        target.push(items[i]);
    }
}

function trySearch(keyword) {
    var encoded =
        encodeURIComponent(
            String(
                keyword || ''
            )
        );

    var urls = [
        SITE + '/?s=' + encoded,
        SITE + '/search/?q=' + encoded,
        SITE + '/movies/search/?q=' + encoded
    ];

    for (var i = 0; i < urls.length; i++) {
        try {
            var html =
                requestPage(
                    urls[i],
                    SITE + '/',
                    SEARCH_TIMEOUT
                );

            var list =
                matchKeyword(
                    parseMovieList(
                        html
                    ),
                    keyword
                );

            if (list.length) {
                return list;
            }
        } catch (error) {
        }
    }

    return [];
}

function fallbackSearch(keyword) {
    var categories = [
        'update',
        'rank',
        '1',
        '2',
        '3',
        '4',
        '5',
        '6'
    ];

    var all = [];
    var seen = {};

    for (var i = 0; i < categories.length; i++) {
        try {
            appendUnique(
                all,
                parseMovieList(
                    requestPage(
                        categoryURL(
                            categories[i]
                        ),
                        SITE + '/',
                        SEARCH_TIMEOUT
                    )
                ),
                seen
            );
        } catch (error) {
        }
    }

    return matchKeyword(
        all,
        keyword
    );
}


/* =========================================================
 * CATVOD API
 * ========================================================= */

function apiInit(ext) {
    return '';
}

function apiHome(filter) {
    return json({
        'class': [
            { type_id: 'update', type_name: '最新更新' },
            { type_id: 'rank', type_name: '熱門排行' },
            { type_id: '1', type_name: '穿越古代' },
            { type_id: '2', type_name: '都市情愛' },
            { type_id: '3', type_name: '復仇爽劇' },
            { type_id: '4', type_name: '玄幻武俠' },
            { type_id: '5', type_name: '奇幻懸疑' },
            { type_id: '6', type_name: '其他短劇' }
        ]
    });
}

function apiHomeVod() {
    var url =
        SITE +
        '/movies/update/';

    if (isAndroidRuntime()) {
        return requestPageAsyncRetry(
            url,
            SITE + '/',
            RETRY_TIMEOUT,
            RETRY_ATTEMPTS
        ).then(function(html) {
            var list =
                html
                    ? parseMovieList(
                        html
                    )
                    : [];

            if (list.length > 30) {
                list =
                    list.slice(
                        0,
                        30
                    );
            }

            return json({
                list: list
            });
        });
    }

    var html =
        requestPageSyncRetry(
            url,
            SITE + '/',
            PAGE_TIMEOUT,
            2
        );

    var list =
        html
            ? parseMovieList(
                html
            )
            : [];

    if (list.length > 30) {
        list =
            list.slice(
                0,
                30
            );
    }

    return json({
        list: list
    });
}

function buildCategoryResult(html, page) {
    var list =
        html
            ? parseMovieList(
                html
            )
            : [];

    return json({
        list: list,
        page: page,
        pagecount: 1,
        limit: list.length || 30,
        total: list.length
    });
}

function apiCategory(
    tid,
    pg,
    filter,
    extend
) {
    var page =
        parseInt(
            pg || '1',
            10
        ) || 1;

    if (page !== 1) {
        return json({
            list: [],
            page: page,
            pagecount: 1,
            limit: 30,
            total: 0
        });
    }

    var url =
        categoryURL(
            tid
        );

    if (isAndroidRuntime()) {
        return requestPageAsyncRetry(
            url,
            SITE + '/',
            RETRY_TIMEOUT,
            RETRY_ATTEMPTS
        ).then(function(html) {
            return buildCategoryResult(
                html,
                page
            );
        });
    }

    return buildCategoryResult(
        requestPageSyncRetry(
            url,
            SITE + '/',
            PAGE_TIMEOUT,
            2
        ),
        page
    );
}

function buildDetailResult(value, html) {
    if (!html) {
        return json({ list: [] });
    }

    var episodes =
        parseEpisodes(
            html,
            value
        );

    if (!episodes.length) {
        return json({ list: [] });
    }

    return json({
        list: [
            {
                vod_id: value,
                vod_name: detailTitle(html),
                vod_pic: '',
                vod_remarks:
                    episodes.length +
                    '集',
                vod_content: detailDescription(html),
                vod_play_from: '8Movie',
                vod_play_url:
                    episodes.join('#')
            }
        ]
    });
}

function apiDetail(id) {
    var value =
        String(
            id || ''
        );

    var match =
        /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(
            value
        );

    if (match) {
        value = match[1];
    }

    if (!/^\d+$/.test(value)) {
        return json({ list: [] });
    }

    var page =
        SITE +
        '/movies/' +
        value +
        '/';

    if (isAndroidRuntime()) {
        return requestPageAsyncRetry(
            page,
            SITE + '/',
            RETRY_TIMEOUT,
            RETRY_ATTEMPTS
        ).then(function(html) {
            return buildDetailResult(
                value,
                html
            );
        });
    }

    return buildDetailResult(
        value,
        requestPageSyncRetry(
            page,
            SITE + '/',
            PAGE_TIMEOUT,
            2
        )
    );
}

function apiPlay(
    flag,
    id,
    vipFlags
) {
    var playPage =
        absolute(
            id,
            SITE + '/'
        );

    return json({
        parse: 1,
        url: playPage,
        header: {
            'User-Agent': UA,
            'Referer': SITE + '/'
        }
    });
}

function trySearchAsync(
    keyword,
    index
) {
    var encoded =
        encodeURIComponent(
            String(
                keyword || ''
            )
        );

    var urls = [
        SITE + '/?s=' + encoded,
        SITE + '/search/?q=' + encoded,
        SITE + '/movies/search/?q=' + encoded
    ];

    var current =
        index || 0;

    if (current >= urls.length) {
        return Promise.resolve([]);
    }

    return requestPageAsyncRetry(
        urls[current],
        SITE + '/',
        RETRY_TIMEOUT,
        RETRY_ATTEMPTS
    ).then(function(html) {
        var list =
            matchKeyword(
                parseMovieList(
                    html
                ),
                keyword
            );

        if (list.length) {
            return list;
        }

        return trySearchAsync(
            keyword,
            current + 1
        );
    });
}

function apiSearch(
    key,
    quick,
    pg
) {
    var keyword =
        clean(
            key
        );

    if (!keyword) {
        return json({ list: [] });
    }

    if (isAndroidRuntime()) {
        return trySearchAsync(
            keyword,
            0
        ).then(function(list) {
            return json({
                list: list,
                page: 1,
                pagecount: 1,
                limit:
                    list.length ||
                    20,
                total:
                    list.length
            });
        });
    }

    var list = [];

    try {
        list =
            trySearch(
                keyword
            );
    } catch (error) {
        list = [];
    }

    if (!list.length) {
        try {
            list =
                fallbackSearch(
                    keyword
                );
        } catch (error2) {
            list = [];
        }
    }

    return json({
        list: list,
        page: 1,
        pagecount: 1,
        limit:
            list.length ||
            20,
        total:
            list.length
    });
}

/* =========================================================
 * SHARED SPIDER
 * ========================================================= */

function createSpider() {
    return {
        init: apiInit,
        home: apiHome,
        homeVod: apiHomeVod,
        category: apiCategory,
        detail: apiDetail,
        play: apiPlay,
        search: apiSearch
    };
}


/* iOS */
globalThis.__jsEvalReturn =
    createSpider;


/* Android */
ensureRequestBridge();

var androidSpiderKey =
    '__JS_' +
    'SPIDER__';

if (
    !globalThis[
        androidSpiderKey
    ]
) {
    globalThis[
        androidSpiderKey
    ] =
        createSpider();
}
