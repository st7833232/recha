/*
 * WebHTV CatVod JS Spider - 8Movie
 * Fast / JS-only version
 *
 * - No image proxy
 * - No per-card detail request
 * - No WebHTV app modification
 * - Playback: parse:1 -> MediaSniffer
 */

var SITE = 'https://www.8movie.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';


function requestHeaders() {
    return {
        'User-Agent': UA,
        'Referer': SITE + '/',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8'
    };
}


function http(url) {
    var result = req(url, {
        method: 'GET',
        headers: requestHeaders(),
        timeout: 20000
    }) || {};

    return result.content || result.body || '';
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


function absolute(value) {
    var url = clean(value);

    if (!url) {
        return '';
    }

    if (/^https?:\/\//i.test(url)) {
        return url;
    }

    if (url.indexOf('//') === 0) {
        return 'https:' + url;
    }

    if (url.charAt(0) === '/') {
        return SITE + url;
    }

    return SITE + '/' + url.replace(/^\.\//, '');
}


function movieId(value) {
    var match =
        /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(
            String(value || '')
        );

    return match
        ? match[1]
        : '';
}


function isCategoryId(id) {
    return /^(1|2|3|4|5|6)$/.test(
        String(id || '')
    );
}


function playInfo(value) {
    var match =
        /\/play\/(\d+)\/(\d+)\/?(?:[?#].*)?$/i.exec(
            String(value || '')
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


function extractTitle(node) {
    var title =
        clean(
            pdfh(node, 'a&&title') ||
            pdfh(node, 'img&&alt') ||
            pdfh(node, 'a&&Text') ||
            pdfh(node, 'Text') ||
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

    return clean(title);
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
            ) || '';

        var id =
            movieId(href);


        if (!id) {
            continue;
        }


        /*
         * /movies/1/ ～ /movies/6/
         * are category pages, not movies.
         */
        if (
            isCategoryId(id)
        ) {
            continue;
        }


        if (
            seen[id]
        ) {
            continue;
        }


        var title =
            extractTitle(
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

            /*
             * Intentionally blank.
             *
             * 8Movie direct artwork currently returns the
             * site's promotional/fallback image when loaded
             * by WebHTV AsyncImage.
             *
             * Leaving this blank is better than displaying
             * the wrong artwork and keeps list loading fast.
             */
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


    return clean(value);
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
            ) || '';

        var info =
            playInfo(href);


        if (!info) {
            continue;
        }


        if (
            String(info.movie) !==
            String(id)
        ) {
            continue;
        }


        if (
            seen[info.path]
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
                String(
                    parseInt(
                        info.episode,
                        10
                    )
                );


            while (
                number.length < 3
            ) {
                number =
                    '0' + number;
            }


            label =
                '第' +
                number +
                '集';
        }


        result.push(
            label +
            '$' +
            absolute(
                info.path
            )
        );


        seen[
            info.path
        ] = true;
    }


    return result;
}


function categoryUrl(tid) {
    tid =
        String(
            tid || 'update'
        );


    if (
        tid === 'update'
    ) {
        return (
            SITE +
            '/movies/update/'
        );
    }


    if (
        tid === 'rank'
    ) {
        return (
            SITE +
            '/movies/rank/'
        );
    }


    if (
        /^[1-6]$/.test(
            tid
        )
    ) {
        return (
            SITE +
            '/movies/' +
            tid +
            '/'
        );
    }


    return (
        SITE +
        '/movies/update/'
    );
}


function matchKeyword(
    list,
    keyword
) {
    var result = [];

    var key =
        clean(
            keyword
        ).toLowerCase();

    var i;


    for (
        i = 0;
        i < list.length;
        i++
    ) {
        if (
            String(
                list[i].vod_name ||
                ''
            )
                .toLowerCase()
                .indexOf(key) !== -1
        ) {
            result.push(
                list[i]
            );
        }
    }


    return result;
}


function appendUnique(
    output,
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


        output.push(
            items[i]
        );
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
            var list =
                matchKeyword(
                    parseMovieList(
                        http(
                            urls[i]
                        )
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
                        categoryUrl(
                            categories[i]
                        )
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


function apiInit(ext) {
    return '';
}


function apiHome(filter) {
    return {
        'class': [
            {
                type_id: 'update',
                type_name: '最新更新'
            },

            {
                type_id: 'rank',
                type_name: '熱門排行'
            },

            {
                type_id: '1',
                type_name: '穿越古代'
            },

            {
                type_id: '2',
                type_name: '都市情愛'
            },

            {
                type_id: '3',
                type_name: '復仇爽劇'
            },

            {
                type_id: '4',
                type_name: '玄幻武俠'
            },

            {
                type_id: '5',
                type_name: '奇幻懸疑'
            },

            {
                type_id: '6',
                type_name: '其他短劇'
            }
        ]
    };
}


function apiHomeVod() {
    var list =
        parseMovieList(
            http(
                SITE +
                '/movies/update/'
            )
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


    return {
        list: list
    };
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
        );


    if (
        !page ||
        page < 1
    ) {
        page = 1;
    }


    /*
     * Pagination URL has not yet been verified.
     * Avoid repeating page 1 as fake later pages.
     */
    if (
        page !== 1
    ) {
        return {
            list: [],
            page: page,
            pagecount: 1,
            limit: 30,
            total: 0
        };
    }


    var list =
        parseMovieList(
            http(
                categoryUrl(
                    tid
                )
            )
        );


    return {
        list: list,
        page: 1,
        pagecount: 1,
        limit:
            list.length || 30,
        total:
            list.length
    };
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
        value =
            match[1];
    }


    if (
        !/^\d+$/.test(
            value
        )
    ) {
        return {
            list: []
        };
    }


    var url =
        SITE +
        '/movies/' +
        value +
        '/';


    /*
     * Only one detail request is made when the user
     * actually opens a title.
     */
    var html =
        http(url);


    var episodeList =
        parseEpisodes(
            html,
            value
        );


    if (
        !episodeList.length
    ) {
        return {
            list: []
        };
    }


    return {
        list: [
            {
                vod_id:
                    value,

                vod_name:
                    detailTitle(
                        html
                    ),

                /*
                 * Intentionally blank for the same reason
                 * as list posters.
                 */
                vod_pic:
                    '',

                vod_remarks:
                    episodeList.length +
                    '集',

                vod_content:
                    detailDescription(
                        html
                    ),

                vod_play_from:
                    '8Movie',

                vod_play_url:
                    episodeList.join(
                        '#'
                    )
            }
        ]
    };
}


function apiPlay(
    flag,
    id,
    vipFlags
) {
    /*
     * This is the path already confirmed working.
     *
     * WebHTV:
     * parse:1
     * -> MediaSniffer
     * -> real media URL
     * -> AVPlayer / MPV
     */
    return {
        parse: 1,

        url:
            absolute(
                id
            ),

        header: {
            'User-Agent':
                UA,

            'Referer':
                SITE + '/'
        }
    };
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
        return {
            list: []
        };
    }


    var list =
        trySearch(
            keyword
        );


    if (
        !list.length
    ) {
        list =
            fallbackSearch(
                keyword
            );
    }


    return {
        list: list
    };
}


/*
 * WebHTV CatVod JS Spider entry point
 */
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