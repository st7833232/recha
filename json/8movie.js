var SITE = 'https://www.8movie.com';

var UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
  'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 ' +
  'Mobile/15E148 Safari/604.1';

var HEADERS = {
  'User-Agent': UA,
  'Referer': SITE + '/',
  'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8'
};

function http(url, options) {
  options = options || {};
  options.headers = Object.assign({}, HEADERS, options.headers || {});

  var res = req(url, options) || {};
  return res.content || res.body || '';
}

function absolute(url) {
  url = String(url || '').trim();

  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (url.indexOf('//') === 0) return 'https:' + url;
  if (url.charAt(0) === '/') return SITE + url;

  return SITE + '/' + url.replace(/^\.\//, '');
}

function movieId(href) {
  var m = /\/movies\/(\d+)\/?(?:[?#].*)?$/i.exec(String(href || ''));
  return m ? m[1] : '';
}

function playPath(href) {
  var m = /\/play\/(\d+)\/(\d+)\/?(?:[?#].*)?$/i.exec(String(href || ''));

  return m
    ? '/play/' + m[1] + '/' + m[2] + '/'
    : '';
}

function cleanText(s) {
  return String(s || '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function itemName(node) {
  return cleanText(
    pdfh(node, 'a&&title') ||
    pdfh(node, 'img&&alt') ||
    pdfh(node, 'a&&Text') ||
    pdfh(node, 'Text')
  ).replace(/^\d+集\s*/, '');
}

function itemPic(node) {
  return absolute(
    pdfh(
      node,
      'img&&data-original||data-src||data-lazy-src||src'
    ) ||
    pdfh(
      node,
      'a&&data-original||data-src'
    )
  );
}

function parseMovies(html) {
  var nodes = pdfa(html, 'a[href*="/movies/"]');

  var order = [];
  var map = {};

  for (var i = 0; i < nodes.length; i++) {
    var href = pdfh(nodes[i], 'a&&href') || '';
    var id = movieId(href);

    if (!id) continue;

    var raw = cleanText(
      pdfh(nodes[i], 'a&&Text') ||
      pdfh(nodes[i], 'Text')
    );

    var name = itemName(nodes[i]);

    if (/^(立即觀看|開始觀看|更多|More)$/i.test(name)) {
      name = '';
    }

    var pic = itemPic(nodes[i]);
    var rm = /(\d+)\s*集/.exec(raw);

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
      name &&
      !/^\d+集$/.test(name) &&
      !map[id].vod_name
    ) {
      map[id].vod_name = name;
    }

    if (
      pic &&
      !map[id].vod_pic
    ) {
      map[id].vod_pic = pic;
    }

    if (
      rm &&
      !map[id].vod_remarks
    ) {
      map[id].vod_remarks = rm[1] + '集';
    }
  }

  return order
    .map(function (id) {
      return map[id];
    })
    .filter(function (item) {
      return !!item.vod_name;
    });
}

function firstMeta(html, property, name) {
  var value = '';

  if (property) {
    value = pdfh(
      html,
      'meta[property="' + property + '"]&&content'
    );
  }

  if (!value && name) {
    value = pdfh(
      html,
      'meta[name="' + name + '"]&&content'
    );
  }

  return cleanText(value);
}

function detailName(html) {
  var name = cleanText(
    pdfh(html, 'h1&&Text') ||
    firstMeta(html, 'og:title', '') ||
    pdfh(html, 'title&&Text')
  );

  return name
    .replace(/\s*-\s*8movie\.com.*$/i, '')
    .replace(/\s*-\s*八影短劇網.*$/i, '')
    .trim();
}

function detailPic(html) {
  return absolute(
    firstMeta(html, 'og:image', '') ||
    pdfh(
      html,
      'main img&&data-original||data-src||src'
    ) ||
    pdfh(
      html,
      'article img&&data-original||data-src||src'
    )
  );
}

function detailDescription(html) {
  var text = firstMeta(
    html,
    'og:description',
    'description'
  );

  if (text) return text;

  var heads = pdfa(html, 'h6');

  for (var i = 0; i < heads.length; i++) {
    var s = cleanText(
      pdfh(heads[i], 'Text')
    );

    if (
      s.length > 20 &&
      s.indexOf('溫馨提示') === -1
    ) {
      return s;
    }
  }

  return '';
}

function episodes(html, id) {
  var nodes = pdfa(
    html,
    'a[href*="/play/"]'
  );

  var out = [];
  var seen = {};

  for (var i = 0; i < nodes.length; i++) {
    var href =
      pdfh(nodes[i], 'a&&href') || '';

    var path = playPath(href);

    if (!path || seen[path]) {
      continue;
    }

    if (
      id &&
      path.indexOf(
        '/play/' + id + '/'
      ) !== 0
    ) {
      continue;
    }

    var m =
      /\/play\/\d+\/(\d+)\//.exec(path);

    var n = m
      ? parseInt(m[1], 10)
      : out.length + 1;

    var label = cleanText(
      pdfh(nodes[i], 'a&&Text') ||
      pdfh(nodes[i], 'Text')
    );

    if (!label) {
      label =
        '第' +
        String(n).padStart(3, '0') +
        '集';
    }

    out.push(
      label +
      '$' +
      absolute(path)
    );

    seen[path] = true;
  }

  return out;
}

function categoryURL(tid) {
  if (tid === 'update') {
    return SITE + '/movies/update/';
  }

  if (tid === 'rank') {
    return SITE + '/movies/rank/';
  }

  if (/^[1-6]$/.test(String(tid))) {
    return SITE + '/movies/' + tid + '/';
  }

  return SITE + '/movies/update/';
}

function filterByKeyword(items, key) {
  key = cleanText(key).toLowerCase();

  if (!key) return items;

  return items.filter(function (item) {
    return String(
      item.vod_name || ''
    )
      .toLowerCase()
      .indexOf(key) !== -1;
  });
}

/*
 * 8movie 的搜尋 API 尚未從 Network
 * 確認，因此先嘗試常見搜尋路徑。
 *
 * 如果網站未使用其中任何一種，
 * 會自動進入 searchFallback。
 */
function searchRemote(key) {
  var encoded =
    encodeURIComponent(key);

  var urls = [
    SITE + '/search/?q=' + encoded,
    SITE + '/movies/search/?q=' + encoded,
    SITE + '/?s=' + encoded,
    SITE + '/search/' + encoded + '/'
  ];

  for (var i = 0; i < urls.length; i++) {
    try {
      var items =
        filterByKeyword(
          parseMovies(
            http(urls[i])
          ),
          key
        );

      if (items.length) {
        return items;
      }
    } catch (e) {
    }
  }

  return [];
}

/*
 * 搜尋 endpoint 找不到時，
 * 從最新 / 排行 / 六大分類搜尋。
 *
 * 因此即使官方搜尋介面更動，
 * WebHTV 搜尋仍不會完全失效。
 */
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

  for (var i = 0; i < tids.length; i++) {
    try {
      var items =
        parseMovies(
          http(
            categoryURL(
              tids[i]
            )
          )
        );

      for (
        var j = 0;
        j < items.length;
        j++
      ) {
        if (!seen[items[j].vod_id]) {
          all.push(items[j]);
          seen[
            items[j].vod_id
          ] = true;
        }
      }
    } catch (e) {
    }
  }

  return filterByKeyword(
    all,
    key
  );
}

function init(ext) {
  return '';
}

function home(filter) {
  return {
    class: [
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

function homeVod() {
  return {
    list: parseMovies(
      http(
        SITE +
        '/movies/update/'
      )
    ).slice(0, 30)
  };
}

function category(
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
   * 目前公開頁面沒有確認第二頁 URL，
   * 所以先明確只提供第一頁，
   * 避免錯誤產生重複資料。
   */
  if (page !== 1) {
    return {
      list: [],
      page: page,
      pagecount: 1,
      limit: 30,
      total: 0
    };
  }

  var list =
    parseMovies(
      http(
        categoryURL(
          String(tid)
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

function detail(id) {
  id = String(id || '')
    .replace(
      /^.*\/movies\/(\d+)\/?(?:[?#].*)?$/i,
      '$1'
    );

  if (!/^\d+$/.test(id)) {
    return {
      list: []
    };
  }

  var page =
    SITE +
    '/movies/' +
    id +
    '/';

  var html =
    http(page);

  var eps =
    episodes(
      html,
      id
    );

  if (!eps.length) {
    return {
      list: []
    };
  }

  return {
    list: [
      {
        vod_id: id,

        vod_name:
          detailName(
            html
          ),

        vod_pic:
          detailPic(
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
          eps.join('#')
      }
    ]
  };
}

/*
 * 不猜 8movie 的 CDN。
 *
 * 把 /play/... 頁面交給
 * WebHTV 現有 MediaSniffer。
 *
 * SourceClient 看到 parse:1
 * 會自動執行 sniff。
 */
function play(
  flag,
  id,
  vipFlags
) {
  var url =
    absolute(id);

  return {
    parse: 1,

    url: url,

    header: {
      'User-Agent': UA,
      'Referer':
        SITE + '/'
    }
  };
}

function search(
  key,
  quick,
  pg
) {
  key =
    String(key || '');

  var list =
    searchRemote(key);

  if (!list.length) {
    list =
      searchFallback(key);
  }

  return {
    list: list
  };
}

/*
 * WebHTV ios-poc
 * CatVod JS Spider entry.
 */
export function __jsEvalReturn() {
  return {
    init: init,
    home: home,
    homeVod: homeVod,
    category: category,
    detail: detail,
    play: play,
    search: search
  };
}8movie.js