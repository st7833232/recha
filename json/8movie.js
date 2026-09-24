/*
 * WebHTV CatVod JS Spider - 8Movie
 * Remote source version.
 *
 * Poster fix:
 * 1. Do not treat /movies/1/ ... /movies/6/ as movie IDs.
 * 2. Only accept /p/{movieId}-*.jpg style images as posters.
 */

var SITE = 'https://www.8movie.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';


function baseHeaders() {
    return {
        'User-Agent': UA,
        'Referer': SITE + '/',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8'
    };
}


function mergeHeaders(extra) {
    var out = baseHeaders();
    var key;

    extra = extra || {};

    for (key in extra) {
        if (
            Object.prototype.hasOwnProperty.call(
                extra,
                key
            )
        ) {
            out[key] = extra[key];
        }
    }

    return out;
}


function getText(url, extraHeaders) {
    var result =
        req(
            url,
            {
                method: 'GET',
                headers: mergeHeaders(
                    extraHeaders || {}
                ),
                timeout: 20000
            }
        ) || {};

    return (
        result.content ||
        result.body ||
        ''
    );
}


function trimText(value) {
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
        .replace(/\s+/g, ' ')
        .replace(/^\s+|\s+$/g, '');
}


function absoluteUrl(value) {
    var url = trimText(value);

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

    return (
        SITE +
        '/' +
        url.replace(/^\.\//, '')
    );
}


function movieIdFromUrl(value) {
    var match =
        /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(
            String(value || '')
        );

    return match
        ? match[1]
        : '';
}


function isCategoryMovieId(id) {
    return /^(1|2|3|4|5|6)$/.test(
        String(id || '')
    );
}


function playInfoFromUrl(value) {
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


/*
 * 8Movie genuine poster paths currently use:
 *
 * /p/{movieId}-xxxx.jpg
 */
function posterFromHtmlById(
    html,
    movieId
) {
    var source =
        String(html || '')
            .replace(/\\\//g, '/')
            .replace(/&amp;/gi, '&');

    var id =
        String(movieId || '');

    if (!id) {
        return '';
    }

    var expression =
        new RegExp(
            "(https?:\\/\\/[^\"'<>\\s]+)?" +
            "\\/p\\/" +
            id +
            "[^\"'<>\\s)]*" +
            "\\.(?:jpg|jpeg|png|webp|avif)",
            'i'
        );

    var match =
        expression.exec(source);

    if (!match) {
        return '';
    }

    return absoluteUrl(
        match[0]
    );
}


function validPosterForMovie(
    url,
    movieId
) {
    if (!url) {
        return false;
    }

    var value =
        String(url);

    var id =
        String(movieId || '');

    return (
        value.indexOf(
            '/p/' + id
        ) !== -1
    );
}


function posterFromNode(
    node,
    movieId
) {
    var candidates = [
        pdfh(
            node,
            'img&&data-original'
        ),
        pdfh(
            node,
            'img&&data-src'
        ),
        pdfh(
            node,
            'img&&data-lazy-src'
        ),
        pdfh(
            node,
            'img&&data-url'
        ),
        pdfh(
            node,
            'img&&data-image'
        ),
        pdfh(
            node,
            'img&&src'
        )
    ];

    var i;

    for (
        i = 0;
        i < candidates.length;
        i++
    ) {
        var url =
            absoluteUrl(
                candidates[i]
            );

        if (
            validPosterForMovie(
                url,
                movieId
            )
        ) {
            return url;
        }
    }

    return '';
}


function nodeHref(node) {
    return (
        pdfh(
            node,
            'a&&href'
        ) ||
        ''
    );
}


function nodeText(node) {
    return trimText(
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
}


function parseMovieList(html) {
    var nodes =
        pdfa(
            html,
            'a[href*="/movies/"]'
        );

    var map = {};
    var order = [];
    var i;


    for (
        i = 0;
        i < nodes.length;
        i++
    ) {

        var href =
            nodeHref(
                nodes[i]
            );

        var id =
            movieIdFromUrl(
                href
            );


        if (!id) {
            continue;
        }


        if (
            isCategoryMovieId(id)
        ) {
            continue;
        }


        var raw =
            nodeText(
                nodes[i]
            );


        var title =
            trimText(
                pdfh(
                    nodes[i],
                    'a&&title'
                ) ||
                pdfh(
                    nodes[i],
                    'img&&alt'
                ) ||
                raw
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


        title =
            trimText(
                title
            );


        if (
            !title ||
            /^More$/i.test(title) ||
            title === '分類' ||
            title === '最新' ||
            title === '排行' ||
            title === '標籤'
        ) {
            continue;
        }


        var remark = '';

        var remarkMatch =
            /(\d+)\s*集/.exec(
                raw
            );


        if (remarkMatch) {
            remark =
                remarkMatch[1] +
                '集';
        }


        if (!map[id]) {

            map[id] = {
                vod_id: id,
                vod_name: '',
                vod_pic: '',
                vod_remarks: ''
            };

            order.push(id);
        }


        if (
            !map[id].vod_name
        ) {
            map[id].vod_name =
                title;
        }


        if (
            !map[id].vod_pic
        ) {

            map[id].vod_pic =
                posterFromHtmlById(
                    html,
                    id
                );
        }


        if (
            !map[id].vod_pic
        ) {

            map[id].vod_pic =
                posterFromNode(
                    nodes[i],
                    id
                );
        }


        if (
            remark &&
            !map[id].vod_remarks
        ) {

            map[id].vod_remarks =
                remark;
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


        if (
            item &&
            item.vod_name
        ) {
            list.push(
                item
            );
        }
    }


    return list;
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


    return trimText(
        value
    );
}


function detailName(html) {
    var value =
        trimText(
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


    return trimText(
        value
    );
}


function detailPicture(
    html,
    movieId
) {
    var poster =
        posterFromHtmlById(
            html,
            movieId
        );


    if (poster) {
        return poster;
    }


    var values = [
        metaContent(
            html,
            'og:image',
            ''
        ),

        pdfh(
            html,
            'main img&&data-original'
        ),

        pdfh(
            html,
            'main img&&data-src'
        ),

        pdfh(
            html,
            'main img&&src'
        ),

        pdfh(
            html,
            'article img&&data-original'
        ),

        pdfh(
            html,
            'article img&&data-src'
        ),

        pdfh(
            html,
            'article img&&src'
        )
    ];


    var i;


    for (
        i = 0;
        i < values.length;
        i++
    ) {

        var url =
            absoluteUrl(
                values[i]
            );


        if (
            validPosterForMovie(
                url,
                movieId
            )
        ) {
            return url;
        }
    }


    return '';
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
            trimText(
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
    movieId
) {
    var nodes =
        pdfa(
            html,
            'a[href*="/play/"]'
        );


    var seen = {};
    var out = [];
    var i;


    for (
        i = 0;
        i < nodes.length;
        i++
    ) {

        var href =
            nodeHref(
                nodes[i]
            );


        var info =
            playInfoFromUrl(
                href
            );


        if (!info) {
            continue;
        }


        if (
            String(info.movie) !==
            String(movieId)
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
            nodeText(
                nodes[i]
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


        out.push(
            label +
            '$' +
            absoluteUrl(
                info.path
            )
        );


        seen[
            info.path
        ] = true;
    }


    return out;
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


function containsKeyword(
    item,
    keyword
) {
    return (
        String(
            item.vod_name ||
            ''
        )
            .toLowerCase()
            .indexOf(
                String(
                    keyword || ''
                ).toLowerCase()
            ) !== -1
    );
}


function filterKeyword(
    items,
    keyword
) {
    var out = [];
    var i;


    for (
        i = 0;
        i < items.length;
        i++
    ) {

        if (
            containsKeyword(
                items[i],
                keyword
            )
        ) {

            out.push(
                items[i]
            );
        }
    }


    return out;
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

            appendUnique(
                all,

                parseMovieList(
                    getText(
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


    return filterKeyword(
        all,
        keyword
    );
}


function trySiteSearch(keyword) {
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
                filterKeyword(

                    parseMovieList(
                        getText(
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
            getText(
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
     * Pagination URL has not been verified yet.
     * Do not fake additional pages.
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
            getText(
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


    var page =
        SITE +
        '/movies/' +
        value +
        '/';


    var html =
        getText(
            page
        );


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
                    detailName(
                        html
                    ),

                vod_pic:
                    detailPicture(
                        html,
                        value
                    ),

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
    var url =
        absoluteUrl(
            id
        );


    return {

        parse: 1,

        url: url,

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
        trimText(
            key
        );


    if (
        !keyword
    ) {

        return {
            list: []
        };
    }


    var list =
        trySiteSearch(
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