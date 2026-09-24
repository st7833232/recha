/*
 * WebHTV CatVod JS Spider - 8Movie
 * Remote source
 *
 * v3:
 * - Actual posters are fetched from each movie detail page.
 * - Category IDs 1-6 are excluded from movie results.
 * - Detail HTML / posters use in-memory cache.
 * - Playback remains parse:1 -> WebHTV MediaSniffer.
 */

var SITE = 'https://www.8movie.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';

var DETAIL_CACHE = {};
var POSTER_CACHE = {};


function headers() {
    return {
        'User-Agent': UA,
        'Referer': SITE + '/',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8'
    };
}


function http(url) {
    var res = req(url, {
        method: 'GET',
        headers: headers(),
        timeout: 20000
    }) || {};

    return res.content || res.body || '';
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

    return match ? match[1] : '';
}


function isCategoryId(id) {
    return /^(1|2|3|4|5|6)$/.test(
        String(id || '')
    );
}


function movieUrl(id) {
    return SITE + '/movies/' + id + '/';
}


function detailHtml(id) {
    id = String(id || '');

    if (!id) {
        return '';
    }

    if (DETAIL_CACHE[id] !== undefined) {
        return DETAIL_CACHE[id];
    }

    var html = '';

    try {
        html = http(
            movieUrl(id)
        );
    } catch (e) {
        html = '';
    }

    DETAIL_CACHE[id] = html;

    return html;
}


function metaContent(
    html,
    propertyName,
    nameValue
) {
    var value = '';

    if (propertyName) {
        value = pdfh(
            html,
            'meta[property="' +
                propertyName +
                '"]&&content'
        );
    }

    if (!value && nameValue) {
        value = pdfh(
            html,
            'meta[name="' +
                nameValue +
                '"]&&content'
        );
    }

    return clean(value);
}


/*
 * The actual 8Movie movie artwork uses:
 *
 * /p/{movieId}-xxxx.jpg
 *
 * Example:
 * /p/15610-kytq.jpg
 */
function exactPosterFromHtml(
    html,
    id
) {
    var source =
        String(html || '')
            .replace(/\\\//g, '/')
            .replace(/&amp;/gi, '&');

    var movie =
        String(id || '');

    if (!movie) {
        return '';
    }

    var pattern =
        new RegExp(
            "(https?:\\/\\/[^\"'<>\\s]+)?" +
            "\\/p\\/" +
            movie +
            "[^\"'<>\\s)]*" +
            "\\.(?:jpg|jpeg|png|webp|avif)",
            'i'
        );

    var match =
        pattern.exec(source);

    if (!match) {
        return '';
    }

    return absolute(
        match[0]
    );
}


function posterForMovie(id) {
    id = String(id || '');

    if (!id) {
        return '';
    }

    if (POSTER_CACHE[id] !== undefined) {
        return POSTER_CACHE[id];
    }

    var html =
        detailHtml(id);

    var poster =
        exactPosterFromHtml(
            html,
            id
        );


    /*
     * Fallback to og:image only when it still belongs
     * to this movie's /p/{id} image.
     */
    if (!poster) {
        var og =
            absolute(
                metaContent(
                    html,
                    'og:image',
                    ''
                )
            );

        if (
            og &&
            og.indexOf(
                '/p/' + id
            ) !== -1
        ) {
            poster = og;
        }
    }


    /*
     * Try ordinary images in the detail page,
     * but never accept the generic 8movie image.
     */
    if (!poster) {
        var images =
            pdfa(
                html,
                'img'
            );

        var i;

        for (
            i = 0;
            i < images.length;
            i++
        ) {
            var src =
                absolute(
                    pdfh(
                        images[i],
                        'img&&data-original'
                    ) ||
                    pdfh(
                        images[i],
                        'img&&data-src'
                    ) ||
                    pdfh(
                        images[i],
                        'img&&data-lazy-src'
                    ) ||
                    pdfh(
                        images[i],
                        'img&&src'
                    )
                );

            if (
                src &&
                src.indexOf(
                    '/p/' + id
                ) !== -1
            ) {
                poster = src;
                break;
            }
        }
    }

    POSTER_CACHE[id] =
        poster || '';

    return POSTER_CACHE[id];
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


function parseList(
    html,
    loadPosters
) {
    var nodes =
        pdfa(
            html,
            'a[href*="/movies/"]'
        );

    var order = [];
    var map = {};
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

        if (isCategoryId(id)) {
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
                )
            );


        var title =
            clean(
                pdfh(
                    nodes[i],
                    'a&&title'
                ) ||
                pdfh(
                    nodes[i],
                    'img&&alt'
                ) ||
                text
            );


        title =
            title
                .replace(
                    /^\s*\d+\s*集\s*/,
                    ''
                )
                .replace(
                    /^立即觀看\s*/i,
                    ''
                );


        title =
            clean(title);


        if (
            !title ||
            title === '分類' ||
            title === '最新' ||
            title === '排行' ||
            title === '標籤' ||
            /^More$/i.test(title)
        ) {
            continue;
        }


        var episodeMatch =
            /(\d+)\s*集/.exec(
                text
            );


        if (!map[id]) {
            map[id] = {
                vod_id: id,
                vod_name: title,
                vod_pic: '',
                vod_remarks:
                    episodeMatch
                        ? episodeMatch[1] + '集'
                        : ''
            };

            order.push(id);
        }


        if (
            !map[id].vod_name &&
            title
        ) {
            map[id].vod_name =
                title;
        }


        if (
            !map[id].vod_remarks &&
            episodeMatch
        ) {
            map[id].vod_remarks =
                episodeMatch[1] +
                '集';
        }
    }


    var list = [];


    for (
        i = 0;
        i < order.length;
        i++
    ) {
        var item =
            map[
                order[i]
            ];

        if (!item) {
            continue;
        }


        if (loadPosters) {
            item.vod_pic =
                posterForMovie(
                    item.vod_id
                );
        }


        list.push(item);
    }


    return list;
}


function enrichPosters(list) {
    var i;

    for (
        i = 0;
        i < list.length;
        i++
    ) {
        if (
            list[i] &&
            list[i].vod_id
        ) {
            list[i].vod_pic =
                posterForMovie(
                    list[i].vod_id
                );
        }
    }

    return list;
}


function categoryUrl(tid) {
    tid =
        String(
            tid || 'update'
        );


    if (tid === 'update') {
        return SITE +
            '/movies/update/';
    }


    if (tid === 'rank') {
        return SITE +
            '/movies/rank/';
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


    return SITE +
        '/movies/update/';
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
            )
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


function description(html) {
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
                )
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


function episodes(
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
            String(
                info.movie
            ) !==
            String(id)
        ) {
            continue;
        }


        if (
            seen[
                info.path
            ]
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
                )
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
                    '0' +
                    number;
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


function keywordMatch(
    list,
    keyword
) {
    var result = [];
    var key =
        String(
            keyword || ''
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


function uniqueAppend(
    destination,
    source,
    seen
) {
    var i;


    for (
        i = 0;
        i < source.length;
        i++
    ) {
        var id =
            String(
                source[i].vod_id ||
                ''
            );


        if (
            !id ||
            seen[id]
        ) {
            continue;
        }


        seen[id] = true;

        destination.push(
            source[i]
        );
    }
}


function searchSite(keyword) {
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
                keywordMatch(
                    parseList(
                        http(
                            urls[i]
                        ),
                        false
                    ),
                    keyword
                );


            if (
                list.length
            ) {
                return enrichPosters(
                    list
                );
            }
        } catch (e) {
        }
    }


    return [];
}


function searchFallback(keyword) {
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
            uniqueAppend(
                all,
                parseList(
                    http(
                        categoryUrl(
                            categories[i]
                        )
                    ),
                    false
                ),
                seen
            );
        } catch (e) {
        }
    }


    return enrichPosters(
        keywordMatch(
            all,
            keyword
        )
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
        parseList(
            http(
                SITE +
                '/movies/update/'
            ),
            true
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
        parseList(
            http(
                categoryUrl(
                    tid
                )
            ),
            true
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


    var html =
        detailHtml(
            value
        );


    var episodeList =
        episodes(
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

                vod_pic:
                    posterForMovie(
                        value
                    ),

                vod_remarks:
                    episodeList.length +
                    '集',

                vod_content:
                    description(
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
        searchSite(
            keyword
        );


    if (
        !list.length
    ) {
        list =
            searchFallback(
                keyword
            );
    }


    return {
        list: list
    };
}


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