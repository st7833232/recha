/*
 * WebHTV CatVod JS Spider - KKYS
 * Target: https://www.kkys20.com
 *
 * Remote JS Spider for WebHTV ios-poc.
 *
 * Features:
 * - correct title parsing
 * - correct KKYS poster host handling
 * - category filters
 * - pagination
 * - dynamic search token
 * - true multi-line playback
 * - line / episode index pairing
 * - excludes special 4K line
 * - direct playSource URL extraction
 * - dujia / PPPP AES-ECB decryption
 * - MediaSniffer fallback
 */

var SITE = 'https://www.kkys20.com';

var IMG_HOST = 'https://vres.esadj.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';

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
    var result =
        req(
            url,
            {
                method: 'GET',

                headers:
                    requestHeaders(
                        referer
                    ),

                timeout:
                    20000
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
            String(
                url || ''
            )
        );


    return match
        ? match[1]
        : '';
}


function absolute(value, base) {
    var url =
        clean(
            value
        );


    var root =
        base || SITE + '/';


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
 * Image
 * ========================================================= */

function rewriteImage(value) {
    var raw =
        clean(
            value
        );


    if (!raw) {
        return '';
    }


    raw =
        raw.replace(
            /\\\//g,
            '/'
        );


    if (
        /logo_placeholder|placeholder_vertical/i.test(
            raw
        )
    ) {
        return '';
    }


    /*
     * Already points at one of KKYS' image CDNs.
     */
    if (
        /^https?:\/\//i.test(
            raw
        )
    ) {
        var sourceHost =
            originOf(
                raw
            );


        if (
            /vres\./i.test(
                sourceHost
            ) ||
            /:\d+$/i.test(
                sourceHost
            )
        ) {
            return raw;
        }


        /*
         * The site can publish its own host in
         * data-original even though the actual
         * image files live on vres.
         */
        if (
            sourceHost ===
            originOf(
                SITE
            )
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


function imageFromModule(node) {
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
        var url =
            rewriteImage(
                values[i]
            );


        if (url) {
            return url;
        }
    }


    return '';
}


/* =========================================================
 * Filters
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
    allowScore
) {
    var result = [
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


    if (
        allowScore
    ) {
        result.push(
            option(
                '評分',
                '4'
            )
        );
    }


    return {
        key: 'sort',
        name: '排序',
        value: result
    };
}


var YEARS =
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

            [
                '10年代',
                '2010_2019'
            ],

            [
                '00年代',
                '2000_2009'
            ],

            [
                '90年代',
                '1990_1999'
            ],

            [
                '80年代',
                '1980_1989'
            ],

            [
                '更早',
                '0_1979'
            ]
        ]
    );


var LANGUAGES =
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


var MOVIE_AREAS =
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
            ['丹麥', '丹麦'],
            ['瑞典', '瑞典'],
            ['巴西', '巴西'],
            ['加拿大', '加拿大'],
            ['俄羅斯', '俄罗斯'],
            ['義大利', '意大利'],
            ['比利時', '比利时'],
            ['愛爾蘭', '爱尔兰'],
            ['西班牙', '西班牙'],
            ['澳大利亞', '澳大利亚'],
            ['其他', '其他']
        ]
    );


var SERIES_AREAS =
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


var ANIME_AREAS =
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
            ['丹麥', '丹麦'],
            ['瑞典', '瑞典'],
            ['巴西', '巴西'],
            ['加拿大', '加拿大'],
            ['俄羅斯', '俄罗斯'],
            ['義大利', '意大利'],
            ['比利時', '比利时'],
            ['愛爾蘭', '爱尔兰'],
            ['西班牙', '西班牙'],
            ['澳大利亞', '澳大利亚'],
            ['其他', '其他']
        ]
    );


var VARIETY_AREAS =
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
                ['歌舞', '歌舞'],
                ['短片', '短片'],
                ['動畫', '动画'],
                ['兒童', '儿童'],
                ['職場', '职场']
            ]
        ),

        MOVIE_AREAS,
        LANGUAGES,
        YEARS,
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
                ['言情', '言情'],
                ['恐怖', '恐怖'],
                ['冒險', '冒险'],
                ['都市', '都市'],
                ['職場', '职场']
            ]
        ),

        SERIES_AREAS,
        LANGUAGES,
        YEARS,
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
                ['兒童', '儿童'],
                ['搞笑', '搞笑'],
                ['愛情', '爱情'],
                ['家庭', '家庭'],
                ['短片', '短片'],
                ['熱血', '热血'],
                ['益智', '益智'],
                ['懸疑', '悬疑'],
                ['經典', '经典'],
                ['校園', '校园'],
                ['Anime', 'Anime'],
                ['運動', '运动'],
                ['親子', '亲子'],
                ['青春', '青春'],
                ['戀愛', '恋爱'],
                ['武俠', '武侠'],
                ['驚悚', '惊悚']
            ]
        ),

        ANIME_AREAS,
        LANGUAGES,
        YEARS,
        sortRow(true)
    ],


    '4': [
        filterRow(
            'type',
            '類型',
            [
                ['紀錄', '纪录'],
                ['真人秀', '真人秀'],
                ['記錄', '记录'],
                ['脫口秀', '脱口秀'],
                ['劇情', '剧情'],
                ['歷史', '历史'],
                ['喜劇', '喜剧'],
                ['傳記', '传记'],
                ['相聲', '相声'],
                ['節目', '节目'],
                ['歌舞', '歌舞'],
                ['冒險', '冒险'],
                ['運動', '运动'],
                ['Season', 'Season'],
                ['犯罪', '犯罪'],
                ['短片', '短片'],
                ['搞笑', '搞笑'],
                ['晚會', '晚会']
            ]
        ),

        VARIETY_AREAS,
        LANGUAGES,
        YEARS,
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
                ['戰爭', '战争'],
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
            String(
                value || ''
            )
        );


    return match
        ? match[1]
        : '';
}


function moduleTitle(node) {
    /*
     * Current KKYS structure:
     * .v-item-title:eq(1)
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
        )
    );
}


function moduleRemark(node) {
    var remark =
        clean(
            pdfh(
                node,
                'span:eq(-1)&&Text'
            )
        );


    return remark;
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
                'a.v-item&&href'
            ) ||
            pdfh(
                nodes[i],
                'a&&href'
            ) ||
            '';


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
                imageFromModule(
                    nodes[i]
                ),

            vod_remarks:
                moduleRemark(
                    nodes[i]
                )
        });


        seen[id] =
            true;
    }


    return result;
}


/* =========================================================
 * Category
 * ========================================================= */

function buildShowURL(
    tid,
    page,
    extend
) {
    extend =
        extend || {};


    var type =
        extend.type ||
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


    var sort =
        extend.sort ||
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
            String(
                tid
            )
        ) +

        '-' +

        encodeURIComponent(
            type
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
            sort
        ) +

        '-' +

        pg +

        '.html'
    );
}


function hasNextPage(html) {
    if (
        String(
            html || ''
        ).indexOf(
            'page-item-next'
        ) !== -1
    ) {
        return true;
    }


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
 * Detail
 * ========================================================= */

function detailTitle(html) {
    /*
     * KKYS injects hidden watermark strong elements.
     * The visible title is normally the second strong.
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
    var pic =
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
        );


    return rewriteImage(
        pic
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
    var value =
        clean(
            pdfh(
                html,
                '.detail-info-row-main:eq(-2)&&Text'
            )
        );


    if (value) {
        return value;
    }


    return clean(
        pdfh(
            html,
            '.detail-tags&&Text'
        )
    );
}


/* =========================================================
 * Lines / episodes
 * ========================================================= */

function trueLineName(node, index) {
    /*
     * IMPORTANT:
     *
     * Do not read the last span.
     *
     * On the site:
     *
     * 超清2
     * 秒播/4K
     *
     * "超清2" is source-item-label.
     * "秒播/4K" is only the subtitle.
     */
    var name =
        clean(
            pdfh(
                node,
                '.source-item-label&&Text'
            )
        );


    if (!name) {
        name =
            '線路' +
            (index + 1);
    }


    return name;
}


function skipLine(name) {
    /*
     * Current KKYS implementations exclude
     * the dedicated 4K source.
     *
     * This DOES NOT remove 超清2, because its
     * true label is 超清2 even though its subtitle
     * says 秒播/4K.
     */
    return /4k/i.test(
        clean(
            name
        )
    );
}


function uniqueLineName(
    name,
    used
) {
    var base =
        clean(
            name
        ) || '線路';


    if (
        !used[base]
    ) {
        used[base] = 1;

        return base;
    }


    used[base]++;


    return (
        base +
        ' ' +
        used[base]
    );
}


function parsePlayLists(html) {
    /*
     * Website structure:
     *
     * div.source-list-box-main
     *   a.source-item
     *     span.source-item-label
     *
     * div.episode-list-box-main
     *   div.episode-list
     *
     * The two arrays correspond by index.
     */

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


    /*
     * Fallback for minor markup changes.
     */
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

    var usedNames = {};

    var count =
        Math.min(
            sources.length,
            lists.length
        );


    var i;


    for (
        i = 0;
        i < count;
        i++
    ) {
        /*
         * Pair FIRST, filter SECOND.
         *
         * Otherwise skipping a source would shift
         * every later episode list by one line.
         */
        var name =
            trueLineName(
                sources[i],
                i
            );


        if (
            skipLine(
                name
            )
        ) {
            continue;
        }


        var anchors =
            pdfa(
                lists[i],
                'a[href*="/play/"]'
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


            seen[href] =
                true;
        }


        if (
            !episodes.length
        ) {
            continue;
        }


        name =
            uniqueLineName(
                name,
                usedNames
            );


        froms.push(
            name
        );


        urls.push(
            episodes.join(
                '#'
            )
        );
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
 * Search token
 * ========================================================= */

function searchToken(html) {
    var token =
        pdfh(
            html,
            'input[name=t]&&value'
        );


    if (token) {
        return clean(
            token
        );
    }


    var source =
        String(
            html || ''
        );


    var match =
        /<input[^>]*name=["']t["'][^>]*value=["']([^"']+)["']/i.exec(
            source
        );


    if (!match) {
        match =
            /<input[^>]*value=["']([^"']+)["'][^>]*name=["']t["']/i.exec(
                source
            );
    }


    return match
        ? clean(
            match[1]
        )
        : '';
}


function searchRequest(
    keyword,
    page
) {
    var encoded =
        encodeURIComponent(
            keyword
        );


    /*
     * First request obtains a fresh token.
     *
     * This mirrors current working KKYS spiders.
     */
    var seedURL =
        SITE +
        '/search?k=' +
        encoded;


    var seedHTML =
        http(
            seedURL,
            SITE + '/'
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
        encodeURIComponent(
            token
        );


    if (
        parseInt(
            page || '1',
            10
        ) > 1
    ) {
        url +=
            '&page=' +
            parseInt(
                page,
                10
            );
    }


    return http(
        url,
        seedURL
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
            detailId(
                href
            );


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
                    'img&&alt'
                )
            );


        if (!name) {
            name =
                clean(
                    pdfh(
                        nodes[i],
                        '.title&&Text'
                    )
                );
        }


        if (!name) {
            continue;
        }


        var pic =
            rewriteImage(
                pdfh(
                    nodes[i],
                    'img&&data-original'
                ) ||
                pdfh(
                    nodes[i],
                    'img&&data-src'
                )
            );


        result.push({
            vod_id:
                id,

            vod_name:
                name,

            vod_pic:
                pic,

            vod_remarks:
                clean(
                    pdfh(
                        nodes[i],
                        '.search-result-item-header&&Text'
                    )
                )
        });


        seen[id] =
            true;
    }


    return result;
}


/* =========================================================
 * Playback
 * ========================================================= */

function unescapeMediaURL(value) {
    return clean(
        value
    )
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
}


function encryptedPlayerURL(html) {
    /*
     * Matches:
     *
     * PPPP = '...'
     * DPPPP = '...'
     * TMDPPPP = '...'
     *
     * The suffix PPPP is what matters.
     */
    var match =
        /PPPP\s*=\s*['"]([^'"]+)['"]/i.exec(
            String(
                html || ''
            )
        );


    if (
        !match ||
        !match[1]
    ) {
        return '';
    }


    try {
        var decrypted =
            host.aesDecrypt(
                match[1],
                AES_KEY,
                '',
                'ECB',
                'base64'
            );


        return unescapeMediaURL(
            decrypted
        );

    } catch (error) {
        return '';
    }
}


function normalPlayerURL(html) {
    var source =
        String(
            html || ''
        );


    /*
     * Most KKYS lines expose:
     *
     * const playSource = {
     *     src: "https://...m3u8"
     * }
     */
    var patterns = [

        /playSource\s*=\s*\{[\s\S]*?src\s*:\s*"([^"]+)"/i,

        /playSource\s*=\s*\{[\s\S]*?src\s*:\s*'([^']+)'/i,

        /src\s*:\s*"([^"]+\.(?:m3u8|mp4|flv|mkv|webm)[^"]*)"/i,

        /src\s*:\s*'([^']+\.(?:m3u8|mp4|flv|mkv|webm)[^']*)'/i,

        /"(https?:\/\/[^"]+\.m3u8[^"]*)"/i,

        /'(https?:\/\/[^']+\.m3u8[^']*)'/i,

        /"(https?:\/\/[^"]+\.(?:mp4|flv|mkv|webm)[^"]*)"/i,

        /'(https?:\/\/[^']+\.(?:mp4|flv|mkv|webm)[^']*)'/i
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


    if (!html) {
        return '';
    }


    var media = '';


    /*
     * Some KKYS exclusive lines use PPPP +
     * AES-ECB.
     */
    if (
        /dujia/i.test(
            html
        ) ||
        /PPPP\s*=/i.test(
            html
        )
    ) {
        media =
            encryptedPlayerURL(
                html
            );
    }


    /*
     * Normal playSource.src path.
     */
    if (!media) {
        media =
            normalPlayerURL(
                html
            );
    }


    if (!media) {
        return '';
    }


    return absolute(
        media,
        SITE + '/'
    );
}


/* =========================================================
 * CatVod methods
 * ========================================================= */

function apiInit(ext) {
    return '';
}


function apiHome(filter) {
    return {

        'class': [

            {
                type_id:
                    '1',

                type_name:
                    '電影'
            },

            {
                type_id:
                    '2',

                type_name:
                    '連續劇'
            },

            {
                type_id:
                    '3',

                type_name:
                    '動漫'
            },

            {
                type_id:
                    '4',

                type_name:
                    '綜藝紀錄'
            },

            {
                type_id:
                    '6',

                type_name:
                    '短劇'
            }
        ],

        filters:
            FILTERS
    };
}


function apiHomeVod() {
    var html =
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
        list:
            list
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
        ) || 1;


    var url =
        buildShowURL(
            String(
                tid
            ),
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


    var next =
        hasNextPage(
            html
        );


    return {
        list:
            list,

        page:
            page,

        pagecount:
            next
                ? page + 1
                : page,

        limit:
            list.length ||
            18,

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


    if (!html) {
        return {
            list: []
        };
    }


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


    var media = '';


    try {
        media =
            resolvePlayURL(
                playPage
            );
    } catch (error) {
        media = '';
    }


    /*
     * Normal case:
     * we already extracted the real stream.
     */
    if (media) {
        return {
            parse:
                0,

            url:
                media,

            header: {
                'User-Agent':
                    UA,

                /*
                 * Important:
                 * KKYS streams / TS segments behave better
                 * with the site root as Referer.
                 */
                'Referer':
                    SITE + '/'
            }
        };
    }


    /*
     * Fallback:
     * only when the play page changed and the
     * JS parser could not extract its stream.
     */
    return {
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
        html =
            '';
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


    return {
        list:
            list,

        page:
            page,

        pagecount:
            next
                ? page + 1
                : page,

        limit:
            list.length ||
            20,

        total:
            list.length
    };
}


/* =========================================================
 * WebHTV CatVod JS Spider entry
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