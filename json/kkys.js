/*
 * WebHTV CatVod JS Spider - KKYS20
 * https://www.kkys20.com
 *
 * Features:
 * - categories: movie / series / anime / variety-documentary / short drama
 * - CatVod filters: class / area / lang / year / by
 * - real show pagination
 * - search token from the site's own generated links
 * - search pagination follows the site's own next-page token
 * - multi-line / multi-episode detail parsing
 * - playback delegated to WebHTV MediaSniffer (parse: 1)
 */

var SITE = 'https://www.kkys20.com';

var UA =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
    'Mobile/15E148 Safari/604.1';

var SEARCH_URL_CACHE = {};

function option(n, v) {
    return { n: n, v: v };
}

function row(key, name, values) {
    var out = [option('全部', '')];
    var i;

    for (i = 0; i < values.length; i++) {
        out.push(
            option(
                values[i][0],
                values[i][1]
            )
        );
    }

    return {
        key: key,
        name: name,
        value: out
    };
}

function sortRow(includeScore) {
    var values = [
        option('綜合', '1'),
        option('最新', '2'),
        option('最熱', '3')
    ];

    if (includeScore) {
        values.push(
            option('評分', '4')
        );
    }

    return {
        key: 'by',
        name: '排序',
        value: values
    };
}

var YEAR_ROW = row(
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

var LANG_ROW = row(
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

var AREA_FULL = row(
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

var AREA_SERIES = row(
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

var AREA_VARIETY = row(
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
        row(
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
                ['歌舞', '歌舞'],
                ['短片', '短片'],
                ['動畫', '动画'],
                ['兒童', '儿童'],
                ['職場', '职场']
            ]
        ),

        AREA_FULL,
        LANG_ROW,
        YEAR_ROW,
        sortRow(true)
    ],

    '2': [
        row(
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
                ['言情', '言情'],
                ['恐怖', '恐怖'],
                ['冒險', '冒险'],
                ['都市', '都市'],
                ['職場', '职场']
            ]
        ),

        AREA_SERIES,
        LANG_ROW,
        YEAR_ROW,
        sortRow(true)
    ],

    '3': [
        row(
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

        AREA_FULL,
        LANG_ROW,
        YEAR_ROW,
        sortRow(true)
    ],

    '4': [
        row(
            'class',
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

        AREA_VARIETY,
        LANG_ROW,
        YEAR_ROW,
        sortRow(true)
    ],

    '6': [
        row(
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
                ['戰爭', '战争'],
                ['冒險', '冒险'],
                ['其他', '其它']
            ]
        ),

        sortRow(false)
    ]
};


function headers() {

    return {
        'User-Agent':
            UA,

        'Referer':
            SITE + '/',

        'Accept-Language':
            'zh-TW,zh;q=0.9,en;q=0.8'
    };
}


function http(url) {

    var res =
        req(
            url,
            {
                method:
                    'GET',

                headers:
                    headers(),

                timeout:
                    20000
            }
        ) || {};


    return (
        res.content ||
        res.body ||
        ''
    );
}


function clean(value) {

    return String(
        value === undefined ||
        value === null
            ? ''
            : value
    )
        .replace(
            /&nbsp;/gi,
            ' '
        )
        .replace(
            /&amp;/gi,
            '&'
        )
        .replace(
            /&quot;/gi,
            '"'
        )
        .replace(
            /&#39;/gi,
            "'"
        )
        .replace(
            /&#x27;/gi,
            "'"
        )
        .replace(
            /\s+/g,
            ' '
        )
        .replace(
            /^\s+|\s+$/g,
            ''
        );
}


function absolute(value) {

    var url =
        clean(
            value
        );


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
            SITE +
            url
        );
    }


    return (
        SITE +
        '/' +
        url.replace(
            /^\.\//,
            ''
        )
    );
}


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


function imageFromNode(node) {

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
            absolute(
                candidates[i]
            );


        if (!url) {
            continue;
        }


        if (
            /placeholder|logo_placeholder/i.test(
                url
            )
        ) {
            continue;
        }


        return url;
    }


    return '';
}


function titleFromSearchText(text) {

    var match =
        /^(?:電影|电影|劇集|剧集|動漫|动漫|綜藝|综艺|短劇|短剧)\s+(.+?)\s+(?:19|20)\d{2}\s*\//.exec(
            clean(
                text
            )
        );


    return match
        ? clean(
            match[1]
        )
        : '';
}


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

            ''
        );


    if (
        title &&
        !/可可影视|kekys\.com/i.test(
            title
        )
    ) {
        return title;
    }


    var raw =
        clean(

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


    var fromSearch =
        titleFromSearchText(
            raw
        );


    if (
        fromSearch
    ) {
        return fromSearch;
    }


    var match =
        /可可影视-?kekys\.com\s+(.+?)\s+可可影视-?kekys\.com/i.exec(
            raw
        );


    if (
        match
    ) {
        return clean(
            match[1]
        );
    }


    return (
        title ||
        raw
    );
}


function remarkFromNode(node) {

    var raw =
        clean(

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


    var marker =
        raw.indexOf(
            '可可影视'
        );


    if (
        marker > 0
    ) {
        raw =
            clean(
                raw.slice(
                    0,
                    marker
                )
            );
    }


    raw =
        raw
            .replace(
                /豆瓣\s*:\s*[0-9.]+\s*分/gi,
                ''
            )
            .replace(
                /\bBT\b/gi,
                ''
            )
            .replace(
                /^\s+|\s+$/g,
                ''
            );


    if (
        raw.length > 28
    ) {
        return '';
    }


    return clean(
        raw
    );
}


function parseList(html) {

    var nodes =
        pdfa(
            html,
            'a[href*="/detail/"]'
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
            detailId(
                href
            );


        if (!id) {
            continue;
        }


        if (!map[id]) {

            map[id] = {

                vod_id:
                    id,

                vod_name:
                    '',

                vod_pic:
                    '',

                vod_remarks:
                    ''
            };


            order.push(
                id
            );
        }


        if (
            !map[id].vod_name
        ) {

            var title =
                titleFromNode(
                    nodes[i]
                );


            if (
                title
            ) {
                map[id].vod_name =
                    title;
            }
        }


        if (
            !map[id].vod_pic
        ) {

            var pic =
                imageFromNode(
                    nodes[i]
                );


            if (
                pic
            ) {
                map[id].vod_pic =
                    pic;
            }
        }


        if (
            !map[id].vod_remarks
        ) {

            var remark =
                remarkFromNode(
                    nodes[i]
                );


            if (
                remark
            ) {
                map[id].vod_remarks =
                    remark;
            }
        }
    }


    var out = [];


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
            !item ||
            !item.vod_name
        ) {
            continue;
        }


        out.push(
            item
        );
    }


    return out;
}


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
            /\s*[-–]\s*可可影视.*$/i,
            ''
        );


    value =
        value.replace(
            /𝕜𝕜𝕪𝕤[^\s]*\s*/gi,
            ''
        );


    return clean(
        value
    );
}


function detailPic(
    html,
    title
) {

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
        !/placeholder|logo_placeholder/i.test(
            og
        )
    ) {
        return og;
    }


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

        var alt =
            clean(
                pdfh(
                    images[i],
                    'img&&alt'
                )
            );


        var pic =
            imageFromNode(
                images[i]
            );


        if (!pic) {
            continue;
        }


        if (
            title &&
            alt &&
            alt.indexOf(
                title
            ) !== -1
        ) {
            return pic;
        }
    }


    for (
        i = 0;
        i < images.length;
        i++
    ) {

        var fallback =
            imageFromNode(
                images[i]
            );


        if (
            fallback
        ) {
            return fallback;
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


    if (
        value
    ) {
        return value;
    }


    var selectors = [

        '.module-info-introduction-content&&Text',

        '.module-info-introduction&&Text',

        '.module-info-desc&&Text',

        '.video-info-content&&Text',

        '.detail-content&&Text'
    ];


    var i;


    for (
        i = 0;
        i < selectors.length;
        i++
    ) {

        value =
            clean(
                pdfh(
                    html,
                    selectors[i]
                )
            );


        if (
            value &&
            value.length > 10
        ) {
            return value;
        }
    }


    return '';
}


function cleanLineName(
    value,
    index
) {

    var name =
        clean(
            value
        );


    name =
        name.replace(
            /\s+\d+\s*$/,
            ''
        );


    name =
        name.replace(
            /\s+/g,
            ' '
        );


    if (
        !name ||
        name === '排序'
    ) {

        return (
            '線路' +
            (index + 1)
        );
    }


    return name;
}


function parsePlayLists(html) {

    var tabs =
        pdfa(
            html,
            '.module-tab-item span'
        );


    if (
        !tabs.length
    ) {

        tabs =
            pdfa(
                html,
                '.module-tab-item'
            );
    }


    var lists =
        pdfa(
            html,
            '.module-play-list-content'
        );


    if (
        !lists.length
    ) {

        lists =
            pdfa(
                html,
                '.module-play-list'
            );
    }


    if (
        !lists.length
    ) {

        lists =
            pdfa(
                html,
                'ul.stui-content__playlist'
            );
    }


    if (
        !lists.length
    ) {

        lists =
            pdfa(
                html,
                'ul.content__playlist'
            );
    }


    var froms = [];
    var urls = [];
    var i;


    for (
        i = 0;
        i < lists.length;
        i++
    ) {

        var anchors =
            pdfa(
                lists[i],
                'a[href*="/play/"]'
            );


        var episodes = [];
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
                ) || '';


            if (
                !/\/play\/\d+-\d+-\d+\.html/i.test(
                    href
                )
            ) {
                continue;
            }


            var label =
                clean(

                    pdfh(
                        anchors[j],
                        'a&&Text'
                    ) ||

                    pdfh(
                        anchors[j],
                        'Text'
                    ) ||

                    ''
                );


            if (
                !label
            ) {

                label =
                    '第' +
                    (j + 1) +
                    '集';
            }


            episodes.push(
                label +
                '$' +
                absolute(
                    href
                )
            );
        }


        if (
            !episodes.length
        ) {
            continue;
        }


        froms.push(

            cleanLineName(

                tabs[i]
                    ? pdfh(
                        tabs[i],
                        'Text'
                    )
                    : '',

                i
            )
        );


        urls.push(
            episodes.join(
                '#'
            )
        );
    }


    /*
     * Fallback if KKYS changes playlist container classes.
     *
     * It loses named source grouping, but keeps playback
     * usable instead of returning no episodes.
     */
    if (
        !urls.length
    ) {

        var all =
            pdfa(
                html,
                'a[href*="/play/"]'
            );


        var fallback = [];
        var seen = {};


        for (
            i = 0;
            i < all.length;
            i++
        ) {

            var link =
                pdfh(
                    all[i],
                    'a&&href'
                ) || '';


            if (
                !/\/play\/\d+-\d+-\d+\.html/i.test(
                    link
                )
            ) {
                continue;
            }


            link =
                absolute(
                    link
                );


            if (
                seen[link]
            ) {
                continue;
            }


            seen[link] =
                true;


            var text =
                clean(

                    pdfh(
                        all[i],
                        'a&&Text'
                    ) ||

                    pdfh(
                        all[i],
                        'Text'
                    ) ||

                    ''
                );


            if (
                !text
            ) {

                text =
                    '播放' +
                    (
                        fallback.length +
                        1
                    );
            }


            fallback.push(
                text +
                '$' +
                link
            );
        }


        if (
            fallback.length
        ) {

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
     * KKYS default list is "最熱",
     * whose current route value is 3.
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
            String(
                tid
            )
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

    var anchors =
        pdfa(
            html,
            'a'
        );


    var i;


    for (
        i = 0;
        i < anchors.length;
        i++
    ) {

        var text =
            clean(

                pdfh(
                    anchors[i],
                    'a&&Text'
                ) ||

                pdfh(
                    anchors[i],
                    'Text'
                ) ||

                ''
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


/*
 * KKYS search requires a changing `t=` token.
 *
 * The site's homepage already publishes valid search
 * links such as:
 *
 * /search?k=仙逆&t=...
 *
 * We reuse the site's own current token and only
 * replace the keyword.
 */
function firstSearchURL(keyword) {

    var home =
        http(
            SITE + '/'
        );


    var links =
        pdfa(
            home,
            'a[href*="/search?"][href*="t="]'
        );


    var i;


    for (
        i = 0;
        i < links.length;
        i++
    ) {

        var href =
            pdfh(
                links[i],
                'a&&href'
            ) || '';


        if (
            !href ||
            href.indexOf(
                't='
            ) === -1
        ) {
            continue;
        }


        var encoded =
            encodeURIComponent(
                String(
                    keyword || ''
                )
            );


        if (
            /[?&]k=/.test(
                href
            )
        ) {

            href =
                href.replace(
                    /([?&]k=)[^&]*/i,
                    '$1' +
                    encoded
                );

        } else {

            href +=
                (
                    href.indexOf('?') === -1
                        ? '?'
                        : '&'
                ) +

                'k=' +
                encoded;
        }


        href =
            href
                .replace(
                    /([?&])page=\d+&?/i,
                    '$1'
                )
                .replace(
                    /[?&]$/,
                    ''
                );


        return absolute(
            href
        );
    }


    return '';
}


/*
 * Search page 2+ receives a different `t=`.
 *
 * Do not calculate or reuse it.
 * Read the exact next-page URL generated by KKYS.
 */
function nextSearchURL(
    html,
    nextPage
) {

    var links =
        pdfa(
            html,
            'a[href*="/search?"][href*="t="]'
        );


    var target =
        String(
            nextPage
        );


    var i;


    for (
        i = 0;
        i < links.length;
        i++
    ) {

        var href =
            pdfh(
                links[i],
                'a&&href'
            ) || '';


        var match =
            /(?:[?&])page=(\d+)(?:&|$)/i.exec(
                href
            );


        if (
            match &&
            match[1] === target
        ) {

            return absolute(
                href
            );
        }
    }


    return '';
}


function searchPage(
    keyword,
    page
) {

    var key =
        String(
            keyword || ''
        );


    var pg =
        parseInt(
            page || '1',
            10
        ) || 1;


    if (
        !SEARCH_URL_CACHE[key]
    ) {

        SEARCH_URL_CACHE[key] =
            {};
    }


    var cache =
        SEARCH_URL_CACHE[key];


    /*
     * First page:
     * get the current token from KKYS homepage.
     */
    if (
        !cache[1]
    ) {

        cache[1] =
            firstSearchURL(
                key
            );
    }


    if (
        !cache[1]
    ) {

        return {
            html: '',
            pagecount: 1
        };
    }


    /*
     * Page 2+:
     * follow each site's generated next link,
     * preserving its fresh token.
     */
    var current = 1;


    while (
        current < pg
    ) {

        if (
            !cache[
                current + 1
            ]
        ) {

            var currentHTML =
                http(
                    cache[
                        current
                    ]
                );


            var nextURL =
                nextSearchURL(
                    currentHTML,
                    current + 1
                );


            if (
                !nextURL
            ) {

                return {
                    html: '',
                    pagecount:
                        current
                };
            }


            cache[
                current + 1
            ] =
                nextURL;
        }


        current++;
    }


    var html =
        http(
            cache[pg]
        );


    return {

        html:
            html,

        pagecount:
            hasNextPage(
                html
            )
                ? 9999
                : pg
    };
}


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


        /*
         * This is what makes WebHTV render
         * the filter rows.
         */
        filters:
            FILTERS
    };
}


function apiHomeVod() {

    var list =
        parseList(
            http(
                SITE + '/'
            )
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
            url
        );


    var list =
        parseList(
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
            list.length ||
            18,

        total:
            hasNextPage(
                html
            )
                ? 999999
                : list.length
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

        return {
            list: []
        };
    }


    var html =
        http(
            SITE +
            '/detail/' +
            value +
            '.html'
        );


    var title =
        detailTitle(
            html
        );


    var plays =
        parsePlayLists(
            html
        );


    if (
        !plays.url
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
                    title,

                vod_pic:
                    detailPic(
                        html,
                        title
                    ),

                vod_remarks:
                    '',

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

    /*
     * We intentionally do not hard-code a player CDN.
     *
     * WebHTV loads the KKYS play page and lets
     * its existing MediaSniffer discover the
     * actual playable media request.
     */
    return {

        parse:
            1,

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


    if (
        !keyword
    ) {

        return {
            list: []
        };
    }


    var page =
        parseInt(
            pg || '1',
            10
        ) || 1;


    var result =
        searchPage(
            keyword,
            page
        );


    var list =
        result.html
            ? parseList(
                result.html
            )
            : [];


    return {

        list:
            list,

        page:
            page,

        pagecount:
            result.pagecount,

        limit:
            list.length ||
            20,

        total:
            result.pagecount > page
                ? 999999
                : list.length
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