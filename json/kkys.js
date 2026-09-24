/*
 * WebHTV CatVod JS Spider - KKYS
 * Target: https://www.kkys20.com
 *
 * Features:
 * - proper title extraction
 * - rdul.js image host discovery
 * - data-original poster support
 * - CatVod filters
 * - multi-line playback
 * - episode lists per line
 * - KKYS search token
 * - direct play URL extraction
 * - dujia AES-ECB playback decryption
 */

var SITE = 'https://www.kkys20.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';

var HOME_HTML = '';
var SEARCH_TOKEN = '';
var IMG_HOST = '';

var AES_KEY =
    'Isu7fOAvI6!&IKpAbVdhf&^F';


/* =========================================================
 * Basic helpers
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
        'User-Agent': UA,
        'Referer': referer || SITE + '/',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8'
    };
}


function http(url, referer) {
    var result = req(
        url,
        {
            method: 'GET',
            headers: requestHeaders(
                referer
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


function originOf(url) {
    var match =
        /^(https?:\/\/[^/]+)/i.exec(
            String(url || '')
        );

    return match
        ? match[1]
        : '';
}


function absolute(value, base) {
    var url =
        clean(value);

    var root =
        base || SITE;


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


    var dir =
        String(root)
            .replace(
                /[^/]*$/,
                ''
            );


    return (
        dir +
        url
    );
}


/* =========================================================
 * Bootstrap:
 * - search t token
 * - rdul.js image host
 * ========================================================= */

function discoverSearchToken(html) {
    var token =
        pdfh(
            html,
            'input[name=t]&&value'
        );


    if (!token) {
        var match =
            /<input[^>]+name=["']t["'][^>]+value=["']([^"']+)["']/i.exec(
                String(html || '')
            );


        if (!match) {
            match =
                /<input[^>]+value=["']([^"']+)["'][^>]+name=["']t["']/i.exec(
                    String(html || '')
                );
        }


        if (match) {
            token =
                match[1];
        }
    }


    return clean(
        token
    );
}


function normalizeImageHost(value) {
    var host =
        clean(value);


    if (!host) {
        return '';
    }


    host =
        host.replace(
            /\/+$/,
            ''
        );


    if (
        host.indexOf('//') === 0
    ) {
        host =
            'https:' +
            host;
    }


    if (
        !/^https?:\/\//i.test(
            host
        )
    ) {
        host =
            'https://' +
            host.replace(
                /^\/+/,
                ''
            );
    }


    return host;
}


function discoverImageHost(html) {
    var source =
        String(html || '');

    var scriptMatch =
        /<script[^>]+src=["']([^"']*rdul\.js[^"']*)["']/i.exec(
            source
        );


    if (!scriptMatch) {
        return '';
    }


    var scriptURL =
        absolute(
            scriptMatch[1],
            SITE + '/'
        );


    if (!scriptURL) {
        return '';
    }


    var js = '';

    try {
        js =
            http(
                scriptURL,
                SITE + '/'
            );
    } catch (error) {
        return '';
    }


    /*
     * Current KKYS rdul.js exposes its image host
     * as a quoted string.
     */
    var patterns = [
        /['"](https?:\/\/[^'"]+)['"]/i,
        /['"](\/\/[^'"]+)['"]/i,
        /['"]([^'"]+\.[a-z]{2,}[^'"]*)['"]/i
    ];


    var i;


    for (
        i = 0;
        i < patterns.length;
        i++
    ) {
        var match =
            patterns[i].exec(
                js
            );


        if (
            match &&
            match[1]
        ) {
            return normalizeImageHost(
                match[1]
            );
        }
    }


    return '';
}


function bootstrap(force) {
    if (
        HOME_HTML &&
        !force
    ) {
        return;
    }


    try {
        HOME_HTML =
            http(
                SITE + '/'
            );
    } catch (error) {
        HOME_HTML =
            '';
    }


    SEARCH_TOKEN =
        discoverSearchToken(
            HOME_HTML
        );


    IMG_HOST =
        discoverImageHost(
            HOME_HTML
        );
}


/* =========================================================
 * Image handling
 * ========================================================= */

function rewriteImage(value) {
    var raw =
        clean(value);


    if (!raw) {
        return '';
    }


    raw =
        raw.replace(
            /\\\//g,
            '/'
        );


    /*
     * data-original may still contain the KKYS page host,
     * while the real image CDN comes from rdul.js.
     */
    if (IMG_HOST) {

        if (
            /^https?:\/\/[^/]+/i.test(
                raw
            )
        ) {
            var host =
                originOf(
                    raw
                );


            if (
                /kkys|kekys/i.test(
                    host
                ) ||
                host ===
                    originOf(SITE)
            ) {
                return raw.replace(
                    /^https?:\/\/[^/]+/i,
                    IMG_HOST
                );
            }


            return raw;
        }


        if (
            raw.indexOf('//') === 0
        ) {
            return (
                'https:' +
                raw
            );
        }


        if (
            raw.charAt(0) === '/'
        ) {
            return (
                IMG_HOST +
                raw
            );
        }


        return (
            IMG_HOST +
            '/' +
            raw.replace(
                /^\/+/,
                ''
            )
        );
    }


    return absolute(
        raw,
        SITE + '/'
    );
}


function imageFromNode(node) {
    var values = [
        pdfh(
            node,
            'img:eq(-1)&&data-original'
        ),

        pdfh(
            node,
            'img:eq(-1)&&data-src'
        ),

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
            'img&&src'
        )
    ];


    var i;


    for (
        i = 0;
        i < values.length;
        i++
    ) {
        var result =
            rewriteImage(
                values[i]
            );


        if (
            result &&
            !/logo_placeholder|placeholder_vertical/i.test(
                result
            )
        ) {
            return result;
        }
    }


    return '';
}


/* =========================================================
 * Filter definitions
 * ========================================================= */

function option(name, value) {
    return {
        n: name,
        v: value
    };
}


function filterRow(
    key,
    name,
    values
) {
    var result = [
        option(
            '全部',
            ''
        )
    ];

    var i;


    for (
        i = 0;
        i < values.length;
        i++
    ) {
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


function sortRow(
    withScore
) {
    var values = [
        option(
            '綜合',
            '1'
        ),

        option(
            '最新',
            '2'
        ),

        option(
            '最熱',
            '3'
        )
    ];


    if (withScore) {
        values.push(
            option(
                '評分',
                '4'
            )
        );
    }


    return {
        key: 'by',
        name: '排序',
        value: values
    };
}


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
            ['2019', '2019'],
            ['2018', '2018'],
            ['2017', '2017']
        ]
    );


var AREA_FILTER =
    filterRow(
        'area',
        '地區',
        [
            ['大陸', '中国大陆'],
            ['香港', '中国香港'],
            ['台灣', '中国台湾'],
            ['韓國', '韩国'],
            ['美國', '美国'],
            ['日本', '日本'],
            ['英國', '英国'],
            ['法國', '法国'],
            ['德國', '德国'],
            ['泰國', '泰国'],
            ['印度', '印度'],
            ['加拿大', '加拿大'],
            ['其他', '其他']
        ]
    );


var FILTERS = {

    '1': [
        filterRow(
            'class',
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

        AREA_FILTER,
        LANG_FILTER,
        YEAR_FILTER,
        sortRow(true)
    ],


    '2': [
        filterRow(
            'class',
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

        AREA_FILTER,
        LANG_FILTER,
        YEAR_FILTER,
        sortRow(true)
    ],


    '3': [
        filterRow(
            'class',
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

        AREA_FILTER,
        LANG_FILTER,
        YEAR_FILTER,
        sortRow(true)
    ],


    '4': [
        filterRow(
            'class',
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

        AREA_FILTER,
        LANG_FILTER,
        YEAR_FILTER,
        sortRow(true)
    ],


    '6': [
        filterRow(
            'class',
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
 * List parsing
 * ========================================================= */

function detailId(value) {
    var match =
        /\/detail\/(\d+)\.html(?:[?#].*)?$/i.exec(
            String(value || '')
        );


    return match
        ? match[1]
        : '';
}


function moduleTitle(node) {
    /*
     * Real KKYS rule:
     * .v-item-title:eq(1)&&Text
     */
    var title =
        clean(
            pdfh(
                node,
                '.v-item-title:eq(1)&&Text'
            )
        );


    if (title) {
        return title;
    }


    title =
        clean(
            pdfh(
                node,
                '.v-item-title&&Text'
            )
        );


    if (title) {
        return title;
    }


    return clean(
        pdfh(
            node,
            'img&&alt'
        ) ||
        pdfh(
            node,
            'a&&title'
        )
    );
}


function moduleRemark(node) {
    return clean(
        pdfh(
            node,
            'span:eq(-1)&&Text'
        )
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
            detailId(
                href
            );


        if (
            !id ||
            seen[id]
        ) {
            continue;
        }


        var title =
            moduleTitle(
                nodes[i]
            );


        if (!title) {
            continue;
        }


        result.push({
            vod_id:
                id,

            vod_name:
                title,

            vod_pic:
                imageFromNode(
                    nodes[i]
                ),

            vod_remarks:
                moduleRemark(
                    nodes[i]
                )
        });


        seen[id] = true;
    }


    return result;
}


function parseSearchList(html) {
    var nodes =
        pdfa(
            html,
            '.search-result-item'
        );


    if (!nodes.length) {
        return parseModuleList(
            html
        );
    }


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
            detailId(
                href
            );


        if (
            !id ||
            seen[id]
        ) {
            continue;
        }


        var title =
            clean(
                pdfh(
                    nodes[i],
                    'img&&alt'
                )
            );


        if (!title) {
            continue;
        }


        result.push({
            vod_id:
                id,

            vod_name:
                title,

            vod_pic:
                rewriteImage(
                    pdfh(
                        nodes[i],
                        'img&&data-original'
                    ) ||
                    pdfh(
                        nodes[i],
                        'img&&data-src'
                    )
                ),

            vod_remarks:
                clean(
                    pdfh(
                        nodes[i],
                        '.search-result-item-header&&Text'
                    )
                )
        });


        seen[id] = true;
    }


    return result;
}


/* =========================================================
 * Category URL
 * ========================================================= */

function buildShowURL(
    tid,
    page,
    extend
) {
    extend =
        extend || {};


    var cls =
        extend['class'] ||
        '';


    var area =
        extend.area ||
        '';


    var lang =
        extend.lang ||
        '';


    var year =
        extend.year ||
        '';


    /*
     * KKYS normal/default list uses 3 = 最熱.
     */
    var by =
        extend.by ||
        '3';


    var pg =
        parseInt(
            page || '1',
            10
        ) || 1;


    return (
        SITE +
        '/show/' +

        encodeURIComponent(
            String(tid)
        ) +

        '-' +

        encodeURIComponent(
            cls
        ) +

        '-' +

        encodeURIComponent(
            area
        ) +

        '-' +

        encodeURIComponent(
            lang
        ) +

        '-' +

        encodeURIComponent(
            year
        ) +

        '-' +

        encodeURIComponent(
            by
        ) +

        '-' +

        pg +

        '.html'
    );
}


function hasNextPage(html) {
    var links =
        pdfa(
            html,
            'a'
        );


    var i;


    for (
        i = 0;
        i < links.length;
        i++
    ) {
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
 * Detail parsing
 * ========================================================= */

function detailTitle(html) {
    /*
     * Real KKYS detail title:
     * .detail-title strong:eq(1)
     */
    var title =
        clean(
            pdfh(
                html,
                '.detail-title strong:eq(1)&&Text'
            )
        );


    if (title) {
        return title;
    }


    title =
        clean(
            pdfh(
                html,
                '.detail-title strong&&Text'
            )
        );


    if (title) {
        return title;
    }


    title =
        clean(
            pdfh(
                html,
                'title&&Text'
            )
        );


    return title
        .replace(
            /\s*[-–_]\s*可可影视.*$/i,
            ''
        )
        .replace(
            /\s*[-–_]\s*可可影視.*$/i,
            ''
        )
        .replace(
            /高清免费在线观看.*$/i,
            ''
        )
        .replace(
            /高清免费在線觀看.*$/i,
            ''
        )
        .replace(
            /^\s+|\s+$/g,
            ''
        );
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
        )
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
        )
    );
}


/* =========================================================
 * Multi-line / episode parsing
 * ========================================================= */

function shouldSkipLine(name) {
    var value =
        clean(name);


    return (
        value === '4K(高峰不卡)' ||
        value === '4K（高峰不卡）'
    );
}


function lineName(node, index) {
    var name =
        clean(
            pdfh(
                node,
                'span:eq(-1)&&Text'
            )
        );


    if (!name) {
        name =
            clean(
                pdfh(
                    node,
                    'Text'
                )
            );
    }


    if (!name) {
        name =
            '線路' +
            (index + 1);
    }


    return name;
}


function parsePlayLists(html) {
    /*
     * Real structure:
     *
     * tabs  = .source-item
     * lists = .episode-list
     */
    var tabs =
        pdfa(
            html,
            '.source-item'
        );


    var lists =
        pdfa(
            html,
            '.episode-list'
        );


    var froms = [];
    var urls = [];

    var count =
        Math.max(
            tabs.length,
            lists.length
        );


    var i;


    for (
        i = 0;
        i < count;
        i++
    ) {
        var name =
            tabs[i]
                ? lineName(
                    tabs[i],
                    i
                )
                : (
                    '線路' +
                    (i + 1)
                );


        if (
            shouldSkipLine(
                name
            )
        ) {
            continue;
        }


        if (!lists[i]) {
            continue;
        }


        var anchors =
            pdfa(
                lists[i],
                'a'
            );


        var episodes = [];
        var seen = {};
        var j;


        for (
            j = 0;
            j < anchors.length;
            j++
        ) {
            var href =
                pdfh(
                    anchors[j],
                    'a&&href'
                ) ||
                anchors[j].attrs.href ||
                '';


            if (
                href.indexOf(
                    '/play/'
                ) === -1
            ) {
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
            name
        );


        urls.push(
            episodes.join(
                '#'
            )
        );
    }


    /*
     * Last-resort fallback.
     *
     * This should normally never run now.
     */
    if (!urls.length) {
        var all =
            pdfa(
                html,
                'a[href*="/play/"]'
            );


        var fallback = [];
        var fallbackSeen = {};


        for (
            i = 0;
            i < all.length;
            i++
        ) {
            var link =
                absolute(
                    pdfh(
                        all[i],
                        'a&&href'
                    ),
                    SITE + '/'
                );


            if (
                !link ||
                fallbackSeen[link]
            ) {
                continue;
            }


            var text =
                clean(
                    pdfh(
                        all[i],
                        'Text'
                    )
                );


            if (!text) {
                text =
                    '播放' +
                    (fallback.length + 1);
            }


            fallback.push(
                text +
                '$' +
                link
            );


            fallbackSeen[link] =
                true;
        }


        if (fallback.length) {
            froms.push(
                'KKYS'
            );

            urls.push(
                fallback.join(
                    '#'
                )
            );
        }
    }


    return {
        from:
            froms.join(
                '$$$'
            ),

        url:
            urls.join(
                '$$$'
            )
    };
}


/* =========================================================
 * Search
 * ========================================================= */

function currentSearchToken() {
    if (!SEARCH_TOKEN) {
        bootstrap(
            true
        );
    }


    return SEARCH_TOKEN;
}


function searchURL(
    keyword,
    page,
    token
) {
    return (
        SITE +
        '/search?k=' +

        encodeURIComponent(
            keyword
        ) +

        '&page=' +

        encodeURIComponent(
            String(page)
        ) +

        '&t=' +

        encodeURIComponent(
            token || ''
        )
    );
}


function fetchSearch(
    keyword,
    page
) {
    var token =
        currentSearchToken();


    if (!token) {
        return '';
    }


    var url =
        searchURL(
            keyword,
            page,
            token
        );


    var html =
        http(
            url,
            SITE + '/'
        );


    /*
     * KKYS may publish a refreshed token on the
     * returned search page.
     *
     * Only retry when the first response produced
     * no search cards.
     */
    var items =
        pdfa(
            html,
            '.search-result-item'
        );


    if (!items.length) {
        var refreshed =
            discoverSearchToken(
                html
            );


        if (
            refreshed &&
            refreshed !== token
        ) {
            SEARCH_TOKEN =
                refreshed;


            html =
                http(
                    searchURL(
                        keyword,
                        page,
                        refreshed
                    ),
                    url
                );
        }
    }


    return html;
}


/* =========================================================
 * Playback
 * ========================================================= */

function unescapeMediaURL(value) {
    var url =
        clean(value);


    url =
        url
            .replace(
                /\\\//g,
                '/'
            )
            .replace(
                /\\u0026/gi,
                '&'
            )
            .replace(
                /&amp;/gi,
                '&'
            );


    return url;
}


function encryptedDujiaURL(html) {
    var match =
        /PPPP\s*=\s*['"]([^'"]+)['"]/i.exec(
            String(html || '')
        );


    if (
        !match ||
        !match[1]
    ) {
        return '';
    }


    try {
        return unescapeMediaURL(
            host.aesDecrypt(
                match[1],
                AES_KEY,
                '',
                'ECB',
                'base64'
            )
        );
    } catch (error) {
        return '';
    }
}


function normalPlayerURL(html) {
    var source =
        String(html || '');


    var patterns = [
        /src\s*:\s*"([^"]+)"/i,
        /src\s*:\s*'([^']+)'/i,
        /"url"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"/i,
        /'(https?:\/\/[^']+\.(?:m3u8|mp4)[^']*)'/i,
        /"(https?:\/\/[^"]+\.(?:m3u8|mp4)[^"]*)"/i
    ];


    var i;


    for (
        i = 0;
        i < patterns.length;
        i++
    ) {
        var match =
            patterns[i].exec(
                source
            );


        if (
            match &&
            match[1]
        ) {
            return unescapeMediaURL(
                match[1]
            );
        }
    }


    return '';
}


function resolvePlayURL(playPage) {
    var html =
        http(
            playPage,
            SITE + '/'
        );


    var url = '';


    /*
     * The original KKYS rule uses the presence of
     * "dujia" to select the encrypted PPPP branch.
     */
    if (
        /dujia/i.test(
            html
        )
    ) {
        url =
            encryptedDujiaURL(
                html
            );
    }


    if (!url) {
        url =
            normalPlayerURL(
                html
            );
    }


    return url;
}


/* =========================================================
 * CatVod API
 * ========================================================= */

function apiInit(ext) {
    bootstrap(
        false
    );

    return '';
}


function apiHome(filter) {
    bootstrap(
        false
    );


    return {
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

        filters:
            FILTERS
    };
}


function apiHomeVod() {
    bootstrap(
        false
    );


    var html =
        HOME_HTML ||
        http(
            SITE + '/'
        );


    var list =
        parseModuleList(
            html
        );


    if (
        list.length > 60
    ) {
        list =
            list.slice(
                0,
                60
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
    bootstrap(
        false
    );


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
        http(
            url,
            SITE + '/'
        );


    var list =
        parseModuleList(
            html
        );


    return {
        list:
            list,

        page:
            page,

        pagecount:
            hasNextPage(
                html
            )
                ? 9999
                : page,

        limit:
            list.length || 18,

        total:
            hasNextPage(
                html
            )
                ? 999999
                : list.length
    };
}


function apiDetail(id) {
    bootstrap(
        false
    );


    var value =
        String(
            id || ''
        );


    var match =
        /\/detail\/(\d+)\.html/i.exec(
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
        '/detail/' +
        value +
        '.html';


    var html =
        http(
            url,
            SITE + '/'
        );


    var title =
        detailTitle(
            html
        );


    var plays =
        parsePlayLists(
            html
        );


    if (!plays.url) {
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
                    title,

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
                    plays.from,

                vod_play_url:
                    plays.url
            }
        ]
    };
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


    var media =
        '';


    try {
        media =
            resolvePlayURL(
                playPage
            );
    } catch (error) {
        media =
            '';
    }


    /*
     * Preferred path:
     * return the actual media URL.
     */
    if (media) {
        return {
            parse: 0,

            url:
                media,

            header: {
                'User-Agent':
                    UA,

                'Referer':
                    playPage
            }
        };
    }


    /*
     * Fallback only.
     *
     * If KKYS changes its player structure,
     * let WebHTV MediaSniffer have one chance.
     */
    return {
        parse: 1,

        url:
            playPage,

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
    bootstrap(
        false
    );


    var keyword =
        clean(
            key
        );


    if (!keyword) {
        return {
            list: []
        };
    }


    var page =
        parseInt(
            pg || '1',
            10
        ) || 1;


    var html = '';


    try {
        html =
            fetchSearch(
                keyword,
                page
            );
    } catch (error) {
        html =
            '';
    }


    var list =
        html
            ? parseSearchList(
                html
            )
            : [];


    return {
        list:
            list,

        page:
            page,

        pagecount:
            html &&
            hasNextPage(
                html
            )
                ? 9999
                : page,

        limit:
            list.length || 20,

        total:
            html &&
            hasNextPage(
                html
            )
                ? 999999
                : list.length
    };
}


/* =========================================================
 * JS Spider entry
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