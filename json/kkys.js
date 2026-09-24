/*
 * WebHTV Shared CatVod JS Spider - KKYS20
 *
 * iOS + Android shared source.
 * IMPORTANT: no ES-module import/export syntax.
 *
 * Startup strategy:
 * - home() returns classes/filters immediately.
 * - homeVod() returns immediately and performs NO network request.
 * - Android/iOS load the selected category afterwards.
 *
 * This avoids Android SiteApi.homeContent() waiting for a homepage HTTP
 * request before it can publish the home result.
 */

var SITE = 'https://www.kkys20.com';
var IMG_HOST = 'https://vres.esadj.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';

var PAGE_TIMEOUT = 7000;
var PLAY_TIMEOUT = 8000;
var SEARCH_TIMEOUT = 7000;


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

function requestPage(url, referer, timeout) {
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
                headers: requestHeaders(referer),
                timeout: timeout || PAGE_TIMEOUT
            }
        ) || {};

    return result.content || result.body || '';
}

function originOf(url) {
    var match =
        /^(https?:\/\/[^/]+)/i.exec(
            String(url || '')
        );

    return match ? match[1] : '';
}

function absolute(value, base) {
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


/* =========================================================
 * IMAGE
 * ========================================================= */

function rewriteImage(value) {
    var raw = clean(value);

    if (!raw) return '';

    raw = raw.replace(/\\\//g, '/');

    if (
        /logo_placeholder|placeholder_vertical/i.test(raw)
    ) {
        return '';
    }

    if (/^https?:\/\//i.test(raw)) {
        var imageOrigin = originOf(raw);

        if (
            /vres\./i.test(imageOrigin) ||
            /:\d+$/i.test(imageOrigin)
        ) {
            return raw;
        }

        if (imageOrigin === originOf(SITE)) {
            return raw.replace(
                /^https?:\/\/[^/]+/i,
                IMG_HOST
            );
        }

        return raw;
    }

    if (raw.indexOf('//') === 0) {
        return 'https:' + raw;
    }

    if (raw.charAt(0) === '/') {
        return IMG_HOST + raw;
    }

    return IMG_HOST + '/' + raw.replace(/^\/+/, '');
}

function imageFromModule(node) {
    var candidates = [
        pdfh(node, 'img:eq(-1)&&data-original'),
        pdfh(node, 'img:eq(-1)&&data-src'),
        pdfh(node, 'img&&data-original'),
        pdfh(node, 'img&&data-src'),
        pdfh(node, 'img&&src')
    ];

    for (var i = 0; i < candidates.length; i++) {
        var image = rewriteImage(candidates[i]);

        if (image) {
            return image;
        }
    }

    return '';
}


/* =========================================================
 * FILTERS
 * ========================================================= */

function option(name, value) {
    return {
        n: name,
        v: value
    };
}

function filterRow(key, name, values) {
    var result = [
        option('全部', '')
    ];

    for (var i = 0; i < values.length; i++) {
        result.push(
            option(
                values[i][0],
                values[i][1]
            )
        );
    }

    return {
        key: key,
        name: name,
        value: result
    };
}

function sortRow(withScore) {
    var values = [
        option('綜合', '1'),
        option('最新', '2'),
        option('最熱', '3')
    ];

    if (withScore) {
        values.push(
            option('評分', '4')
        );
    }

    return {
        key: 'sort',
        name: '排序',
        value: values
    };
}

var YEAR_FILTER =
    filterRow(
        'year',
        '年代',
        [
            ['2026', '2026'],
            ['2025', '2025'],
            ['2024', '2024'],
            ['2023', '2023'],
            ['2022', '2022'],
            ['2021', '2021'],
            ['2020', '2020'],
            ['10年代', '2010_2019'],
            ['00年代', '2000_2009'],
            ['90年代', '1990_1999'],
            ['80年代', '1980_1989'],
            ['更早', '0_1979']
        ]
    );

var LANG_FILTER =
    filterRow(
        'lang',
        '語言',
        [
            ['國語', '国语'],
            ['粵語', '粤语'],
            ['英語', '英语'],
            ['日語', '日语'],
            ['韓語', '韩语'],
            ['法語', '法语'],
            ['其他', '其他']
        ]
    );

var MOVIE_AREA =
    filterRow(
        'area',
        '地區',
        [
            ['大陸', '中国大陆'],
            ['香港', '中国香港'],
            ['台灣', '中国台湾'],
            ['美國', '美国'],
            ['日本', '日本'],
            ['韓國', '韩国'],
            ['英國', '英国'],
            ['法國', '法国'],
            ['德國', '德国'],
            ['印度', '印度'],
            ['泰國', '泰国'],
            ['加拿大', '加拿大'],
            ['俄羅斯', '俄罗斯'],
            ['義大利', '意大利'],
            ['西班牙', '西班牙'],
            ['澳大利亞', '澳大利亚'],
            ['其他', '其他']
        ]
    );

var SERIES_AREA =
    filterRow(
        'area',
        '地區',
        [
            ['大陸', '中国大陆'],
            ['香港', '中国香港'],
            ['韓國', '韩国'],
            ['美國', '美国'],
            ['日本', '日本'],
            ['法國', '法国'],
            ['英國', '英国'],
            ['德國', '德国'],
            ['台灣', '中国台湾'],
            ['泰國', '泰国'],
            ['印度', '印度'],
            ['其他', '其他']
        ]
    );

var ANIME_AREA =
    filterRow(
        'area',
        '地區',
        [
            ['日本', '日本'],
            ['大陸', '中国大陆'],
            ['台灣', '中国台湾'],
            ['美國', '美国'],
            ['香港', '中国香港'],
            ['韓國', '韩国'],
            ['英國', '英国'],
            ['法國', '法国'],
            ['德國', '德国'],
            ['印度', '印度'],
            ['泰國', '泰国'],
            ['加拿大', '加拿大'],
            ['俄羅斯', '俄罗斯'],
            ['義大利', '意大利'],
            ['西班牙', '西班牙'],
            ['澳大利亞', '澳大利亚'],
            ['其他', '其他']
        ]
    );

var VARIETY_AREA =
    filterRow(
        'area',
        '地區',
        [
            ['大陸', '中国大陆'],
            ['香港', '中国香港'],
            ['台灣', '中国台湾'],
            ['美國', '美国'],
            ['日本', '日本'],
            ['韓國', '韩国'],
            ['其他', '其他']
        ]
    );

var FILTERS = {
    '1': [
        filterRow(
            'type',
            '類型',
            [
                ['劇情', '剧情'],
                ['喜劇', '喜剧'],
                ['動作', '动作'],
                ['愛情', '爱情'],
                ['恐怖', '恐怖'],
                ['驚悚', '惊悚'],
                ['犯罪', '犯罪'],
                ['科幻', '科幻'],
                ['懸疑', '悬疑'],
                ['奇幻', '奇幻'],
                ['冒險', '冒险'],
                ['戰爭', '战争'],
                ['歷史', '历史'],
                ['古裝', '古装'],
                ['家庭', '家庭'],
                ['傳記', '传记'],
                ['武俠', '武侠'],
                ['動畫', '动画']
            ]
        ),
        MOVIE_AREA,
        LANG_FILTER,
        YEAR_FILTER,
        sortRow(true)
    ],

    '2': [
        filterRow(
            'type',
            '類型',
            [
                ['劇情', '剧情'],
                ['愛情', '爱情'],
                ['喜劇', '喜剧'],
                ['犯罪', '犯罪'],
                ['懸疑', '悬疑'],
                ['古裝', '古装'],
                ['動作', '动作'],
                ['家庭', '家庭'],
                ['驚悚', '惊悚'],
                ['奇幻', '奇幻'],
                ['美劇', '美剧'],
                ['科幻', '科幻'],
                ['歷史', '历史'],
                ['戰爭', '战争'],
                ['韓劇', '韩剧'],
                ['武俠', '武侠'],
                ['都市', '都市'],
                ['職場', '职场']
            ]
        ),
        SERIES_AREA,
        LANG_FILTER,
        YEAR_FILTER,
        sortRow(true)
    ],

    '3': [
        filterRow(
            'type',
            '類型',
            [
                ['動態漫畫', '动态漫画'],
                ['劇情', '剧情'],
                ['動畫', '动画'],
                ['喜劇', '喜剧'],
                ['冒險', '冒险'],
                ['動作', '动作'],
                ['奇幻', '奇幻'],
                ['科幻', '科幻'],
                ['搞笑', '搞笑'],
                ['愛情', '爱情'],
                ['家庭', '家庭'],
                ['熱血', '热血'],
                ['懸疑', '悬疑'],
                ['校園', '校园'],
                ['運動', '运动'],
                ['戀愛', '恋爱'],
                ['武俠', '武侠']
            ]
        ),
        ANIME_AREA,
        LANG_FILTER,
        YEAR_FILTER,
        sortRow(true)
    ],

    '4': [
        filterRow(
            'type',
            '類型',
            [
                ['紀錄', '纪录'],
                ['真人秀', '真人秀'],
                ['脫口秀', '脱口秀'],
                ['劇情', '剧情'],
                ['歷史', '历史'],
                ['喜劇', '喜剧'],
                ['傳記', '传记'],
                ['相聲', '相声'],
                ['歌舞', '歌舞'],
                ['運動', '运动'],
                ['晚會', '晚会']
            ]
        ),
        VARIETY_AREA,
        LANG_FILTER,
        YEAR_FILTER,
        sortRow(true)
    ],

    '6': [
        filterRow(
            'type',
            '類型',
            [
                ['王爺太子', '王爷太子'],
                ['霸道總裁', '霸道总裁'],
                ['屌絲逆襲', '屌丝逆袭'],
                ['贅婿系列', '赘婿系列'],
                ['重生系列', '重生系列'],
                ['穿越短劇', '穿越短剧'],
                ['美女總裁', '美女总裁'],
                ['嬌妻系列', '娇妻系列'],
                ['龍王系列', '龙王系列'],
                ['都市言情', '都市言情'],
                ['逆襲', '逆袭'],
                ['甜寵', '甜宠'],
                ['虐戀', '虐恋'],
                ['穿越', '穿越'],
                ['重生', '重生'],
                ['劇情', '剧情'],
                ['科幻', '科幻'],
                ['武俠', '武侠'],
                ['愛情', '爱情'],
                ['動作', '动作'],
                ['冒險', '冒险'],
                ['其他', '其它']
            ]
        ),
        sortRow(false)
    ]
};


/* =========================================================
 * LIST
 * ========================================================= */

function detailId(value) {
    var match =
        /\/detail\/(\d+)\.html(?:[?#].*)?$/i.exec(
            String(value || '')
        );

    return match ? match[1] : '';
}

function moduleTitle(node) {
    return clean(
        pdfh(node, '.v-item-title:eq(1)&&Text') ||
        pdfh(node, '.v-item-title&&Text') ||
        pdfh(node, 'img&&alt') ||
        ''
    );
}

function moduleRemark(node) {
    return clean(
        pdfh(node, '.v-item-bottom&&Text') ||
        pdfh(node, 'span:eq(-1)&&Text') ||
        ''
    );
}

function parseModuleList(html) {
    var nodes =
        pdfa(
            html,
            '.module-item'
        );

    var result = [];
    var seen = {};

    for (var i = 0; i < nodes.length; i++) {
        var href =
            pdfh(nodes[i], 'a.v-item&&href') ||
            pdfh(nodes[i], 'a&&href') ||
            '';

        var id = detailId(href);

        if (!id || seen[id]) {
            continue;
        }

        var title = moduleTitle(nodes[i]);

        if (!title) {
            continue;
        }

        result.push({
            vod_id: id,
            vod_name: title,
            vod_pic: imageFromModule(nodes[i]),
            vod_remarks: moduleRemark(nodes[i])
        });

        seen[id] = true;
    }

    return result;
}


/* =========================================================
 * CATEGORY
 * ========================================================= */

function buildShowURL(tid, page, extend) {
    extend = extend || {};

    var type = extend.type || '';
    var area = extend.area || '';
    var lang = extend.lang || '';
    var year = extend.year || '';
    var sort = extend.sort || '3';

    var pg =
        parseInt(
            page || '1',
            10
        ) || 1;

    return (
        SITE +
        '/show/' +
        encodeURIComponent(String(tid)) +
        '-' +
        encodeURIComponent(type) +
        '-' +
        encodeURIComponent(area) +
        '-' +
        encodeURIComponent(lang) +
        '-' +
        encodeURIComponent(year) +
        '-' +
        encodeURIComponent(sort) +
        '-' +
        pg +
        '.html'
    );
}

function hasNextPage(html) {
    var source = String(html || '');

    if (
        source.indexOf(
            'page-item-next'
        ) !== -1
    ) {
        return true;
    }

    var links = pdfa(html, 'a');

    for (var i = 0; i < links.length; i++) {
        var text =
            clean(
                pdfh(
                    links[i],
                    'Text'
                )
            );

        if (
            text === '下一页' ||
            text === '下一頁'
        ) {
            return true;
        }
    }

    return false;
}


/* =========================================================
 * DETAIL
 * ========================================================= */

function detailTitle(html) {
    var title =
        clean(
            pdfh(
                html,
                '.detail-title strong:eq(1)&&Text'
            ) ||
            pdfh(
                html,
                '.detail-title strong&&Text'
            ) ||
            pdfh(
                html,
                'title&&Text'
            ) ||
            ''
        );

    return title
        .replace(/\s*[-–_]\s*可可影视.*$/i, '')
        .replace(/\s*[-–_]\s*可可影視.*$/i, '')
        .replace(/高清免费在线观看.*$/i, '')
        .replace(/高清免费在線觀看.*$/i, '')
        .replace(/^\s+|\s+$/g, '');
}

function detailPicture(html) {
    return rewriteImage(
        pdfh(
            html,
            '.detail-pic img&&data-original'
        ) ||
        pdfh(
            html,
            '.detail-pic img&&data-src'
        ) ||
        pdfh(
            html,
            '.detail-pic img&&src'
        ) ||
        ''
    );
}

function detailDescription(html) {
    return clean(
        pdfh(
            html,
            '.detail-desc&&Text'
        )
    );
}

function detailRemarks(html) {
    return clean(
        pdfh(
            html,
            '.detail-info-row-main:eq(-2)&&Text'
        ) ||
        pdfh(
            html,
            '.detail-tags&&Text'
        ) ||
        ''
    );
}


/* =========================================================
 * PLAYBACK LINES
 * ========================================================= */

function sourceName(node, index) {
    var name =
        clean(
            pdfh(
                node,
                '.source-item-label&&Text'
            ) ||
            pdfh(
                node,
                'span.source-item-label&&Text'
            ) ||
            ''
        );

    return name || ('線路' + (index + 1));
}

function skipSource(name) {
    return /4k/i.test(
        clean(name)
    );
}

function uniqueName(value, used) {
    var name =
        clean(value) ||
        '線路';

    if (!used[name]) {
        used[name] = 1;
        return name;
    }

    used[name]++;

    return name + ' ' + used[name];
}

function parsePlayLists(html) {
    var sources =
        pdfa(
            html,
            '.source-list-box-main a.source-item'
        );

    var lists =
        pdfa(
            html,
            '.episode-list-box-main .episode-list'
        );

    if (!sources.length) {
        sources =
            pdfa(
                html,
                'a.source-item'
            );
    }

    if (!lists.length) {
        lists =
            pdfa(
                html,
                '.episode-list'
            );
    }

    var froms = [];
    var urls = [];
    var used = {};

    var count =
        Math.min(
            sources.length,
            lists.length
        );

    for (var i = 0; i < count; i++) {
        /*
         * Pair by index before filtering.
         */
        var name =
            sourceName(
                sources[i],
                i
            );

        if (skipSource(name)) {
            continue;
        }

        var anchors =
            pdfa(
                lists[i],
                'a[href*="/play/"]'
            );

        var episodes = [];
        var seen = {};

        for (var j = 0; j < anchors.length; j++) {
            var href =
                pdfh(
                    anchors[j],
                    'a&&href'
                ) ||
                '';

            if (!href) {
                continue;
            }

            href =
                absolute(
                    href,
                    SITE + '/'
                );

            if (
                !href ||
                seen[href]
            ) {
                continue;
            }

            var label =
                clean(
                    pdfh(
                        anchors[j],
                        'Text'
                    )
                );

            if (!label) {
                label =
                    '第' +
                    (j + 1) +
                    '集';
            }

            episodes.push(
                label +
                '$' +
                href
            );

            seen[href] = true;
        }

        if (!episodes.length) {
            continue;
        }

        froms.push(
            uniqueName(
                name,
                used
            )
        );

        urls.push(
            episodes.join('#')
        );
    }

    return {
        from: froms.join('$$$'),
        url: urls.join('$$$')
    };
}


/* =========================================================
 * SEARCH
 * ========================================================= */

function searchToken(html) {
    var token =
        pdfh(
            html,
            'input[name=t]&&value'
        );

    if (token) {
        return clean(token);
    }

    var source =
        String(
            html || ''
        );

    var match =
        /name=["']t["'][^>]*value=["']([^"']+)["']/i.exec(
            source
        );

    if (!match) {
        match =
            /value=["']([^"']+)["'][^>]*name=["']t["']/i.exec(
                source
            );
    }

    return match && match[1]
        ? clean(match[1])
        : '';
}

function searchRequest(keyword, page) {
    var encoded =
        encodeURIComponent(
            keyword
        );

    var seedURL =
        SITE +
        '/search?k=' +
        encoded;

    var seedHTML =
        requestPage(
            seedURL,
            SITE + '/',
            SEARCH_TIMEOUT
        );

    var token =
        searchToken(
            seedHTML
        );

    if (!token) {
        return seedHTML;
    }

    var url =
        SITE +
        '/search?k=' +
        encoded +
        '&t=' +
        encodeURIComponent(token);

    var pg =
        parseInt(
            page || '1',
            10
        ) || 1;

    if (pg > 1) {
        url +=
            '&page=' +
            pg;
    }

    return requestPage(
        url,
        seedURL,
        SEARCH_TIMEOUT
    );
}

function parseSearchList(html) {
    var nodes =
        pdfa(
            html,
            '.search-result-item'
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
            detailId(href);

        if (
            !id ||
            seen[id]
        ) {
            continue;
        }

        var name =
            clean(
                pdfh(
                    nodes[i],
                    '.title&&Text'
                ) ||
                pdfh(
                    nodes[i],
                    'img&&alt'
                ) ||
                ''
            );

        if (!name) {
            continue;
        }

        result.push({
            vod_id: id,
            vod_name: name,
            vod_pic:
                rewriteImage(
                    pdfh(
                        nodes[i],
                        'img&&data-original'
                    ) ||
                    pdfh(
                        nodes[i],
                        'img&&data-src'
                    ) ||
                    ''
                ),
            vod_remarks: ''
        });

        seen[id] = true;
    }

    return result;
}


/* =========================================================
 * PLAYER
 * ========================================================= */

function decodeMediaURL(value) {
    return clean(value)
        .replace(/\\\//g, '/')
        .replace(/\\u0026/gi, '&')
        .replace(/&amp;/gi, '&');
}

function extractPlayerURL(html) {
    var source =
        String(
            html || ''
        );

    var match =
        /playSource\s*=\s*\{[^}]*?src\s*:\s*"([^"]+)"/i.exec(
            source
        );

    if (
        match &&
        match[1]
    ) {
        return decodeMediaURL(
            match[1]
        );
    }

    match =
        /playSource\s*=\s*\{[^}]*?src\s*:\s*'([^']+)'/i.exec(
            source
        );

    if (
        match &&
        match[1]
    ) {
        return decodeMediaURL(
            match[1]
        );
    }

    match =
        /(https?:\/\/[^\s"'<>]+\.m3u8[^\s"'<>]*)/i.exec(
            source
        );

    if (
        match &&
        match[1]
    ) {
        return decodeMediaURL(
            match[1]
        );
    }

    match =
        /(https?:\/\/[^\s"'<>]+\.(?:mp4|flv|mkv|webm)[^\s"'<>]*)/i.exec(
            source
        );

    if (
        match &&
        match[1]
    ) {
        return decodeMediaURL(
            match[1]
        );
    }

    return '';
}

function resolvePlayPage(playPage) {
    var html =
        requestPage(
            playPage,
            SITE + '/',
            PLAY_TIMEOUT
        );

    if (!html) {
        return '';
    }

    var media =
        extractPlayerURL(
            html
        );

    if (!media) {
        return '';
    }

    return absolute(
        media,
        playPage
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
            {
                type_id: '1',
                type_name: '電影'
            },
            {
                type_id: '2',
                type_name: '連續劇'
            },
            {
                type_id: '3',
                type_name: '動漫'
            },
            {
                type_id: '4',
                type_name: '綜藝紀錄'
            },
            {
                type_id: '6',
                type_name: '短劇'
            }
        ],
        filters: FILTERS
    });
}

function apiHomeVod() {
    /*
     * Deliberately NO network request here.
     *
     * Android SiteApi.homeContent() calls:
     *
     *   home()
     *   homeVod()
     *
     * synchronously before publishing the result.
     *
     * Keeping homeVod instant lets the UI render classes first.
     * The first category then loads through category().
     */
    return json({
        list: []
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

    var url =
        buildShowURL(
            String(tid),
            page,
            extend || {}
        );

    var html =
        requestPage(
            url,
            SITE + '/',
            PAGE_TIMEOUT
        );

    var list =
        parseModuleList(
            html
        );

    var next =
        hasNextPage(
            html
        );

    return json({
        list: list,
        page: page,
        pagecount:
            next
                ? page + 1
                : page,
        limit:
            list.length ||
            18,
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
        /\/detail\/(\d+)\.html/i.exec(
            value
        );

    if (match) {
        value = match[1];
    }

    if (!/^\d+$/.test(value)) {
        return json({
            list: []
        });
    }

    var page =
        SITE +
        '/detail/' +
        value +
        '.html';

    var html =
        requestPage(
            page,
            SITE + '/',
            PAGE_TIMEOUT
        );

    if (!html) {
        return json({
            list: []
        });
    }

    var playLists =
        parsePlayLists(
            html
        );

    if (!playLists.url) {
        return json({
            list: []
        });
    }

    return json({
        list: [
            {
                vod_id: value,
                vod_name:
                    detailTitle(
                        html
                    ),
                vod_pic:
                    detailPicture(
                        html
                    ),
                vod_remarks:
                    detailRemarks(
                        html
                    ),
                vod_content:
                    detailDescription(
                        html
                    ),
                vod_play_from:
                    playLists.from,
                vod_play_url:
                    playLists.url
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

    var media = '';

    try {
        media =
            resolvePlayPage(
                playPage
            );
    } catch (error) {
        media = '';
    }

    if (media) {
        return json({
            parse: 0,
            url: media,
            header: {
                'User-Agent': UA,
                'Referer': SITE + '/'
            }
        });
    }

    return json({
        parse: 1,
        url: playPage,
        header: {
            'User-Agent': UA,
            'Referer': SITE + '/'
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
            list: []
        });
    }

    var page =
        parseInt(
            pg || '1',
            10
        ) || 1;

    var html = '';

    try {
        html =
            searchRequest(
                keyword,
                page
            );
    } catch (error) {
        html = '';
    }

    var list =
        html
            ? parseSearchList(
                html
            )
            : [];

    var next =
        html
            ? hasNextPage(
                html
            )
            : false;

    return json({
        list: list,
        page: page,
        pagecount:
            next
                ? page + 1
                : page,
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
