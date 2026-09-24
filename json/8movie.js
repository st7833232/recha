/*
 * WebHTV Shared CatVod JS Spider
 * 8Movie
 *
 * ONE source file for:
 * - WebHTV iOS
 * - WebHTV Android
 *
 * No ES-module export syntax.
 *
 * iOS:
 *   globalThis.__jsEvalReturn
 *
 * Android:
 *   globalThis['__JS_' + 'SPIDER__']
 *
 * Both use the SAME createSpider().
 *
 * Site:
 * https://www.8movie.com
 */

var SITE =
    'https://www.8movie.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';


/* =========================================================
 * JSON RESULT
 * ========================================================= */

function json(value) {
    try {
        return JSON.stringify(
            value === undefined ||
            value === null
                ? {}
                : value
        );
    } catch (error) {
        return '{}';
    }
}


/* =========================================================
 * BASIC
 * ========================================================= */

function clean(value) {
    return String(
        value === undefined ||
        value === null
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
    /*
     * Android's QuickJS environment provides http().
     *
     * iOS already provides req().
     *
     * Make req available when Android is running the
     * source directly as an imported module.
     */
    if (
        typeof globalThis.req !== 'function' &&
        typeof http === 'function'
    ) {
        globalThis.req =
            http;
    }
}


function requestHeaders(referer) {
    return {
        'User-Agent':
            UA,

        'Referer':
            referer ||
            SITE + '/',

        'Accept-Language':
            'zh-TW,zh;q=0.9,en;q=0.8',

        'Accept':
            '*/*'
    };
}


function requestPage(
    url,
    referer
) {
    ensureRequestBridge();


    var request =
        typeof req === 'function'
            ? req
            : globalThis.req;


    if (
        typeof request !== 'function'
    ) {
        return '';
    }


    var result =
        request(
            url,
            {
                method:
                    'GET',

                headers:
                    requestHeaders(
                        referer
                    ),

                timeout:
                    15000
            }
        ) || {};


    /*
     * Android QuickJS:
     *   result.content
     *
     * iOS WebHTV:
     *   result.content alias
     *   result.body fallback
     */
    return (
        result.content ||
        result.body ||
        ''
    );
}


function originOf(url) {
    var match =
        /^(https?:\/\/[^/]+)/i.exec(
            String(
                url || ''
            )
        );


    return match
        ? match[1]
        : '';
}


function absolute(
    value,
    base
) {
    var url =
        clean(
            value
        );


    var root =
        base ||
        SITE + '/';


    if (!url) {
        return '';
    }


    if (
        /^https?:\/\//i.test(
            url
        )
    ) {
        return url;
    }


    if (
        url.indexOf('//') === 0
    ) {
        return (
            'https:' +
            url
        );
    }


    if (
        url.charAt(0) === '/'
    ) {
        return (
            originOf(root) +
            url
        );
    }


    var directory =
        String(root)
            .replace(
                /[^/]*$/,
                ''
            );


    return (
        directory +
        url
    );
}


/* =========================================================
 * URL PARSING
 * ========================================================= */

function movieId(value) {
    var match =
        /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(
            String(
                value || ''
            )
        );


    return match
        ? match[1]
        : '';
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
        movie:
            match[1],

        episode:
            match[2],

        path:
            '/play/' +
            match[1] +
            '/' +
            match[2] +
            '/'
    };
}


/* =========================================================
 * LIST TITLE
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


    /*
     * Some cards include the episode count
     * before the actual title.
     */
    title =
        title.replace(
            /^\s*\d+\s*集\s*/,
            ''
        );


    title =
        title.replace(
            /^立即觀看\s*/i,
            ''
        );


    return clean(
        title
    );
}


/* =========================================================
 * LIST PARSER
 * ========================================================= */

function parseMovieList(html) {
    var nodes =
        pdfa(
            html,
            'a[href*="/movies/"]'
        );


    var result =
        [];

    var seen =
        {};


    var i;


    for (
        i = 0;
        i < nodes.length;
        i++
    ) {
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


        /*
         * /movies/1/
         * ...
         * /movies/6/
         *
         * are category URLs, not videos.
         */
        if (
            isCategoryId(
                id
            )
        ) {
            continue;
        }


        if (
            seen[id]
        ) {
            continue;
        }


        var title =
            titleFromNode(
                nodes[i]
            );


        if (!title) {
            continue;
        }


        /*
         * Navigation items that can also match
         * /movies/ anchors.
         */
        if (
            title === '分類' ||
            title === '最新' ||
            title === '排行' ||
            title === '標籤' ||
            title === '追劇' ||
            title === '會員' ||
            /^More$/i.test(
                title
            )
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
            vod_id:
                id,

            vod_name:
                title,

            /*
             * Intentionally blank.
             *
             * 8Movie previously returned generic
             * promotional artwork instead of the
             * real video poster.
             */
            vod_pic:
                '',

            vod_remarks:
                episodeMatch
                    ? episodeMatch[1] + '集'
                    : ''
        });


        seen[id] =
            true;
    }


    return result;
}


/* =========================================================
 * META
 * ========================================================= */

function metaContent(
    html,
    propertyName,
    nameValue
) {
    var value =
        '';


    if (
        propertyName
    ) {
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


    return clean(
        value
    );
}


/* =========================================================
 * DETAIL TITLE
 * ========================================================= */

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


    value =
        value.replace(
            /\s*-\s*8movie\.com.*$/i,
            ''
        );


    value =
        value.replace(
            /\s*-\s*八影短劇網.*$/i,
            ''
        );


    value =
        value.replace(
            /\s*-\s*8Movie.*$/i,
            ''
        );


    return clean(
        value
    );
}


/* =========================================================
 * DETAIL DESCRIPTION
 * ========================================================= */

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


    var i;


    for (
        i = 0;
        i < nodes.length;
        i++
    ) {
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


    var result =
        [];

    var seen =
        {};


    var i;


    for (
        i = 0;
        i < nodes.length;
        i++
    ) {
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


        /*
         * Recommendation blocks can also contain
         * /play/ URLs.
         *
         * Only retain episodes belonging to the
         * current title.
         */
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
            var episodeNumber =
                parseInt(
                    info.episode,
                    10
                );


            if (
                !episodeNumber
            ) {
                episodeNumber =
                    result.length +
                    1;
            }


            label =
                '第' +
                episodeNumber +
                '集';
        }


        result.push(
            label +
            '$' +
            fullURL
        );


        seen[fullURL] =
            true;
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


    if (
        value === 'update'
    ) {
        return (
            SITE +
            '/movies/update/'
        );
    }


    if (
        value === 'rank'
    ) {
        return (
            SITE +
            '/movies/rank/'
        );
    }


    if (
        /^[1-6]$/.test(
            value
        )
    ) {
        return (
            SITE +
            '/movies/' +
            value +
            '/'
        );
    }


    return (
        SITE +
        '/movies/update/'
    );
}


/* =========================================================
 * SEARCH HELPERS
 * ========================================================= */

function matchKeyword(
    list,
    keyword
) {
    var result =
        [];


    var key =
        clean(
            keyword
        )
            .toLowerCase();


    if (!key) {
        return result;
    }


    var i;


    for (
        i = 0;
        i < list.length;
        i++
    ) {
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
    var i;


    for (
        i = 0;
        i < items.length;
        i++
    ) {
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


        seen[id] =
            true;


        target.push(
            items[i]
        );
    }
}


/* =========================================================
 * SEARCH
 * ========================================================= */

function trySearch(keyword) {
    var encoded =
        encodeURIComponent(
            String(
                keyword ||
                ''
            )
        );


    /*
     * 8Movie has changed its search route before.
     *
     * Try the known lightweight forms first.
     */
    var urls = [

        SITE +
        '/?s=' +
        encoded,

        SITE +
        '/search/?q=' +
        encoded,

        SITE +
        '/movies/search/?q=' +
        encoded
    ];


    var i;


    for (
        i = 0;
        i < urls.length;
        i++
    ) {
        try {
            var html =
                requestPage(
                    urls[i],
                    SITE + '/'
                );


            var list =
                matchKeyword(
                    parseMovieList(
                        html
                    ),
                    keyword
                );


            if (
                list.length
            ) {
                return list;
            }

        } catch (error) {
        }
    }


    return [];
}


function fallbackSearch(keyword) {
    /*
     * Only category pages are requested.
     *
     * No detail-page crawling.
     */
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


    var all =
        [];

    var seen =
        {};


    var i;


    for (
        i = 0;
        i < categories.length;
        i++
    ) {
        try {
            appendUnique(
                all,

                parseMovieList(
                    requestPage(
                        categoryURL(
                            categories[i]
                        ),
                        SITE + '/'
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
 * CATVOD METHODS
 * ========================================================= */

function apiInit(ext) {
    return '';
}


/* =========================================================
 * HOME
 * ========================================================= */

function apiHome(filter) {
    return json({
        'class': [

            {
                type_id:
                    'update',

                type_name:
                    '最新更新'
            },

            {
                type_id:
                    'rank',

                type_name:
                    '熱門排行'
            },

            {
                type_id:
                    '1',

                type_name:
                    '穿越古代'
            },

            {
                type_id:
                    '2',

                type_name:
                    '都市情愛'
            },

            {
                type_id:
                    '3',

                type_name:
                    '復仇爽劇'
            },

            {
                type_id:
                    '4',

                type_name:
                    '玄幻武俠'
            },

            {
                type_id:
                    '5',

                type_name:
                    '奇幻懸疑'
            },

            {
                type_id:
                    '6',

                type_name:
                    '其他短劇'
            }
        ]
    });
}


/* =========================================================
 * HOME VOD
 * ========================================================= */

function apiHomeVod() {
    var html =
        requestPage(
            SITE +
            '/movies/update/',
            SITE + '/'
        );


    var list =
        parseMovieList(
            html
        );


    if (
        list.length > 30
    ) {
        list =
            list.slice(
                0,
                30
            );
    }


    return json({
        list:
            list
    });
}


/* =========================================================
 * CATEGORY
 * ========================================================= */

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


    /*
     * Do not guess an unverified pagination URL.
     */
    if (
        page !== 1
    ) {
        return json({
            list:
                [],

            page:
                page,

            pagecount:
                1,

            limit:
                30,

            total:
                0
        });
    }


    var html =
        requestPage(
            categoryURL(
                tid
            ),
            SITE + '/'
        );


    var list =
        parseMovieList(
            html
        );


    return json({
        list:
            list,

        page:
            1,

        pagecount:
            1,

        limit:
            list.length ||
            30,

        total:
            list.length
    });
}


/* =========================================================
 * DETAIL
 * ========================================================= */

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
        value =
            match[1];
    }


    if (
        !/^\d+$/.test(
            value
        )
    ) {
        return json({
            list:
                []
        });
    }


    var page =
        SITE +
        '/movies/' +
        value +
        '/';


    var html =
        requestPage(
            page,
            SITE + '/'
        );


    if (!html) {
        return json({
            list:
                []
        });
    }


    var episodes =
        parseEpisodes(
            html,
            value
        );


    if (
        !episodes.length
    ) {
        return json({
            list:
                []
        });
    }


    return json({
        list: [
            {
                vod_id:
                    value,

                vod_name:
                    detailTitle(
                        html
                    ),

                /*
                 * Keep blank intentionally.
                 *
                 * Avoid known generic/promo artwork.
                 */
                vod_pic:
                    '',

                vod_remarks:
                    episodes.length +
                    '集',

                vod_content:
                    detailDescription(
                        html
                    ),

                vod_play_from:
                    '8Movie',

                vod_play_url:
                    episodes.join(
                        '#'
                    )
            }
        ]
    });
}


/* =========================================================
 * PLAY
 * ========================================================= */

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


    /*
     * Existing 8Movie playback strategy.
     *
     * Do NOT try to guess/extract a direct stream
     * here.
     *
     * The playback page is handed to the platform
     * sniffer.
     *
     * iOS:
     *   MediaSniffer
     *
     * Android:
     *   native sniff / parse path
     */
    return json({
        parse:
            1,

        url:
            playPage,

        header: {
            'User-Agent':
                UA,

            'Referer':
                SITE + '/'
        }
    });
}


/* =========================================================
 * SEARCH API
 * ========================================================= */

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
        return json({
            list:
                []
        });
    }


    var list =
        [];


    try {
        list =
            trySearch(
                keyword
            );

    } catch (error) {
        list =
            [];
    }


    if (
        !list.length
    ) {
        try {
            list =
                fallbackSearch(
                    keyword
                );

        } catch (error2) {
            list =
                [];
        }
    }


    return json({
        list:
            list,

        page:
            1,

        pagecount:
            1,

        limit:
            list.length ||
            20,

        total:
            list.length
    });
}


/* =========================================================
 * ONE SHARED SPIDER
 * ========================================================= */

function createSpider() {
    return {
        init:
            apiInit,

        home:
            apiHome,

        homeVod:
            apiHomeVod,

        category:
            apiCategory,

        detail:
            apiDetail,

        play:
            apiPlay,

        search:
            apiSearch
    };
}


/* =========================================================
 * iOS ENTRY
 *
 * WebHTV iOS reads this factory.
 *
 * No "export" syntax is used.
 * ========================================================= */

globalThis.__jsEvalReturn =
    createSpider;


/* =========================================================
 * ANDROID ENTRY
 *
 * Android QuickJS ultimately consumes its spider
 * through the __JS_SPIDER__ global.
 *
 * The key is split intentionally so Android's
 * source-level replacement logic does not rewrite
 * this source line itself.
 *
 * The SAME createSpider() is used.
 * ========================================================= */

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