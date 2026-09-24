/*
 * WebHTV Shared CatVod JS Spider
 * 8Movie
 *
 * One file for:
 * - WebHTV iOS
 * - WebHTV Android
 *
 * Shared entry:
 * globalThis.__jsEvalReturn
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
 * RESULT
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


function http(
    url,
    referer
) {
    var result =
        req(
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
     * Android QuickJS uses content.
     * iOS WebHTV also supplies the content alias,
     * while body remains supported as fallback.
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


function parseMovieList(html) {
    var nodes =
        pdfa(
            html,
            'a[href*="/movies/"]'
        );


    var result = [];
    var seen = {};

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
         * /movies/1/ ... /movies/6/
         * are category pages, not titles.
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
         * Remove known navigation items.
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
             * 8Movie often returns its generic
             * promotional image instead of the real
             * title artwork.
             *
             * WebHTV placeholder is preferable to a
             * wrong poster.
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
 * DETAIL
 * ========================================================= */

function metaContent(
    html,
    propertyName,
    nameValue
) {
    var value = '';


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


    var result = [];
    var seen = {};

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
         * Avoid collecting play links belonging
         * to another title shown elsewhere on
         * the page.
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
            label =
                '第' +
                String(
                    parseInt(
                        info.episode,
                        10
                    ) || (
                        result.length +
                        1
                    )
                ) +
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
    var result = [];


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
                keyword || ''
            )
        );


    /*
     * 8Movie has changed search entry forms before,
     * so try a few harmless known URL patterns.
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
                http(
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
     * 8Movie is small enough that the category
     * fallback remains practical.
     *
     * No detail-page requests are made here.
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


    var all = [];
    var seen = {};

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
                    http(
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
 * CATVOD API
 *
 * All methods return JSON STRING.
 *
 * Android Spider.java expects String.
 * iOS WebHTV accepts the same JSON String.
 * ========================================================= */

function apiInit(ext) {
    return '';
}


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


function apiHomeVod() {
    var html =
        http(
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
     * Current 8Movie source does not have a
     * verified paged-category contract.
     *
     * Do not fabricate pagination URLs.
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
        http(
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


function apiDetail(id) {
    var value =
        String(
            id || ''
        );


    var match =
        /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(
            value
        );


    if (
        match
    ) {
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
        http(
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
     * This is the playback route already known
     * to work for 8Movie.
     *
     * The page itself contains the actual stream
     * and should be handled by the platform's
     * sniff pipeline.
     *
     * iOS:
     * MediaSniffer
     *
     * Android:
     * Source/sniffer pipeline
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


    var list = [];


    try {
        list =
            trySearch(
                keyword
            );

    } catch (error) {
        list =
            [];
    }


    /*
     * If the site's own search route produced
     * nothing, search the visible categories.
     */
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
 * SHARED WEBHTV CATVOD JS ENTRY
 *
 * No ES-module "export" here.
 *
 * iOS WebHTV:
 *     globalThis.__jsEvalReturn
 *
 * Android WebHTV:
 *     shared QuickJS bridge also reads
 *     globalThis.__jsEvalReturn
 * ========================================================= */

globalThis.__jsEvalReturn =
    function () {
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
    };