/*
 * WebHTV CatVod JS Spider - 8Movie
 * Remote source version: no app modification required.
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
    var k;

    extra = extra || {};

    for (k in extra) {
        if (Object.prototype.hasOwnProperty.call(extra, k)) {
            out[k] = extra[k];
        }
    }

    return out;
}


function getText(url, extraHeaders) {
    var res = req(url, {
        method: 'GET',
        headers: mergeHeaders(extraHeaders || {}),
        timeout: 20000
    }) || {};

    return res.content || res.body || '';
}


function trimText(value) {
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

    return SITE + '/' + url.replace(/^\.\//, '');
}


function movieIdFromUrl(value) {
    var m =
        /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(
            String(value || '')
        );

    return m ? m[1] : '';
}


function playInfoFromUrl(value) {
    var m =
        /\/play\/(\d+)\/(\d+)\/?(?:[?#].*)?$/i.exec(
            String(value || '')
        );

    if (!m) {
        return null;
    }

    return {
        movie: m[1],
        episode: m[2],
        path:
            '/play/' +
            m[1] +
            '/' +
            m[2] +
            '/'
    };
}


function nodeHref(node) {
    return (
        pdfh(node, 'a&&href') ||
        ''
    );
}


function nodeText(node) {
    return trimText(
        pdfh(node, 'a&&Text') ||
        pdfh(node, 'Text') ||
        ''
    );
}


function nodePicture(node) {
    return absoluteUrl(
        pdfh(
            node,
            'img&&data-original||data-src||data-lazy-src||src'
        ) ||
        pdfh(
            node,
            'a&&data-original||data-src'
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

    var order = [];
    var map = {};
    var i;


    for (i = 0; i < nodes.length; i++) {

        var href =
            nodeHref(nodes[i]);

        var id =
            movieIdFromUrl(href);


        if (!id) {
            continue;
        }


        var raw =
            nodeText(nodes[i]);


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


        var remarkMatch =
            /(\d+)\s*集/.exec(raw);


        var remark =
            remarkMatch
                ? remarkMatch[1] + '集'
                : '';


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
            trimText(title);


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
            title &&
            !map[id].vod_name &&
            !/^More$/i.test(title)
        ) {
            map[id].vod_name =
                title;
        }


        if (
            !map[id].vod_pic
        ) {
            map[id].vod_pic =
                nodePicture(
                    nodes[i]
                );
        }


        if (
            !map[id].vod_remarks &&
            remark
        ) {
            map[id].vod_remarks =
                remark;
        }
    }


    var out = [];


    for (
        i = 0;
        i < order.length;
        i++
    ) {

        var item =
            map[order[i]];


        if (
            item &&
            item.vod_name
        ) {
            out.push(item);
        }
    }


    return out;
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


    return trimText(value);
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


    return trimText(value);
}


function detailPicture(html) {

    return absoluteUrl(

        metaContent(
            html,
            'og:image',
            ''
        ) ||

        pdfh(
            html,
            'main img&&data-original||data-src||src'
        ) ||

        pdfh(
            html,
            'article img&&data-original||data-src||src'
        ) ||

        pdfh(
            html,
            'img&&data-original||data-src||src'
        ) ||

        ''
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


    var heads =
        pdfa(
            html,
            'h6'
        );


    var i;


    for (
        i = 0;
        i < heads.length;
        i++
    ) {

        var text =
            trimText(
                pdfh(
                    heads[i],
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
            movieId &&
            info.movie !==
                String(movieId)
        ) {
            continue;
        }


        if (
            seen[info.path]
        ) {
            continue;
        }


        var label =
            nodeText(
                nodes[i]
            );


        if (!label) {

            var n =
                String(
                    parseInt(
                        info.episode,
                        10
                    )
                );


            while (
                n.length < 3
            ) {
                n =
                    '0' + n;
            }


            label =
                '第' +
                n +
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
    key
) {

    return (
        String(
            item.vod_name ||
            ''
        )
        .toLowerCase()
        .indexOf(
            String(
                key || ''
            )
            .toLowerCase()
        ) !== -1
    );
}


function filterKeyword(
    items,
    key
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
                key
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


function searchFallback(key) {

    var tids = [
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
        i < tids.length;
        i++
    ) {

        try {

            appendUnique(

                all,

                parseMovieList(
                    getText(
                        categoryUrl(
                            tids[i]
                        )
                    )
                ),

                seen
            );

        } catch (e) {
        }
    }


    return filterKeyword(
        all,
        key
    );
}


function trySiteSearch(key) {

    var q =
        encodeURIComponent(
            String(
                key || ''
            )
        );


    var candidates = [

        SITE +
            '/?s=' +
            q,

        SITE +
            '/search/?q=' +
            q,

        SITE +
            '/movies/search/?q=' +
            q
    ];


    var i;


    for (
        i = 0;
        i < candidates.length;
        i++
    ) {

        try {

            var list =
                filterKeyword(

                    parseMovieList(
                        getText(
                            candidates[i]
                        )
                    ),

                    key
                );


            if (
                list.length
            ) {
                return list;
            }

        } catch (e) {
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
     * 目前尚未確認 8Movie 第二頁 URL 格式。
     * 所以先只宣告第一頁，避免重複資料。
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

    var raw =
        String(
            id || ''
        );


    var matched =
        /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(
            raw
        );


    if (matched) {
        raw =
            matched[1];
    }


    if (
        !/^\d+$/.test(
            raw
        )
    ) {

        return {
            list: []
        };
    }


    var pageUrl =
        SITE +
        '/movies/' +
        raw +
        '/';


    var html =
        getText(
            pageUrl
        );


    var eps =
        parseEpisodes(
            html,
            raw
        );


    if (
        !eps.length
    ) {

        return {
            list: []
        };
    }


    return {

        list: [

            {
                vod_id:
                    raw,

                vod_name:
                    detailName(
                        html
                    ),

                vod_pic:
                    detailPicture(
                        html
                    ),

                vod_remarks:
                    eps.length +
                    '集',

                vod_content:
                    detailDescription(
                        html
                    ),

                vod_play_from:
                    '8Movie',

                vod_play_url:
                    eps.join(
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


    /*
     * 不在 Spider 中猜測 CDN URL。
     *
     * parse = 1
     * 讓 WebHTV 現有 MediaSniffer
     * 載入 /play/{id}/{episode}/
     * 再尋找真正 m3u8 / mp4。
     */

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


    /*
     * 如果官方搜尋 URL
     * 沒有命中，就從
     * 最新 / 排行 / 六大分類
     * 搜尋。
     */

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


/*
 * WebHTV ios-poc
 * CatVod JS Spider entry point.
 *
 * 不使用 export function，
 * 直接掛到 globalThis，
 * 避免遠端 JS module rewrite
 * 的語法相容問題。
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