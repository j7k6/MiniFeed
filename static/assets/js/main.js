var lastTimestamp = 0;
var showFeeds = false;
var firstRun = true;
var newItemsNum = 0;
var docTitle = document.title;

var groups, feeds;
var groupId = ''
var feedId = '';


function hashChange() {
  if (window.location.hash) {
    var hash = window.location.hash.substring(1);
    var params = hash.split('/');

    if (params[1] === 'all') {
      groupId, feedId = '';

      Array.from(document.querySelectorAll('.active')).forEach((el) => el.classList.remove('active'));

      document.querySelector('.group.all h3').classList.add('active');

      setToggleNav('group', 'all feeds');
    } else {
      if (params.length === 3) {
        if (params[1] == 'group') {
          groupId = params[2];
        }

        if (params[1] == 'feed') {
          feedId = params[2];
        }
      }
    }
  } else {
    groupId, feedId = ''
  }

  firstRun = true;

  toggleFeeds();

  window.scrollTo(0, 0);

  getItems(0);
} 

function toggleFeeds() {
  document.title = docTitle;
  document.querySelector('.counter').innerText = '';

  var feedsBlock = document.querySelector('.feeds');

  if (showFeeds) {
    feedsBlock.classList.remove('show');
    showFeeds = false;
  } else {
    window.scrollTo(0, 0);

    feedsBlock.classList.add('show');
    showFeeds = true;
  }
}


function setToggleNav(type, id, title='') {
  var groupInfo = document.querySelector('.toggle span.group');
  var feedInfo = document.querySelector('.toggle span.feed');

  groupInfo.innerHTML = '';
  feedInfo.innerHTML = '';
  feedInfo.className = 'feed'

  if (type === 'group') {
    groupInfo.innerHTML = id;
  }

  if (type === 'feed') {
    feedInfo.innerHTML = title;
    feedInfo.classList.add(`feed_${id}`)
  }
}


function getItems(since) {
  var fetchUrl = `/api/getItems?since=${since}`;

  if (feedId !== '') {
    groupId = '';
    fetchUrl = `${fetchUrl}&feed_id=${feedId}`;
  }

  if (groupId !== '') {
    feedId = '';
    fetchUrl = `${fetchUrl}&group_id=${groupId}`;
  }

  if (firstRun) {
    document.querySelector('.items').innerHTML = '';
  } else {
    Array.from(document.querySelectorAll('article')).forEach((el) => el.classList.remove('new'));
  }

  fetch(fetchUrl).then(function(res) {
    return res.json();
  }).then(function(data) {
    if (data.length > 0) {
      console.log(data.length);
      lastTimestamp = data[0].added;

      if (!firstRun) {
        var counterValue;

        newItemsNum += data.length;

        if (newItemsNum > 99) {
          counterValue = '99+';
        } else {
          counterValue = newItemsNum;
        }

        document.querySelector('.counter').innerText = counterValue;
        document.title = `${docTitle} (${counterValue})`;
      }

      data.reverse().forEach(function(item) {
        var feed = feeds.find(f => f.id === item.feed);

        var published = new Intl.DateTimeFormat('en-US', {
          year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric', hour12: false
        }).format(new Date(item.published*1000));

        var lastScrollPos = window.scrollY;

        var newItem = document.createElement('article');

        newItem.innerHTML = `
                <h5 class="feed_${feed.id}">${feed.title}:</h5>\
                <h4><a href="${item.link}" target="_blank">${item.title}</a></h4>\
                <h6>${published}</h6>\
                <p>${item.description}</p>`;

        newItem.classList.add('new');

        document.querySelector('.items').prepend(newItem);

        if (!firstRun && window.scrollY > 0) {
          var prependItem = document.querySelector('.items article:first-child');
          var prependItemStyle = window.getComputedStyle(prependItem);
          var prependItemHeight = prependItem.offsetHeight + parseInt(prependItemStyle.marginTop) + parseInt(prependItemStyle.marginBottom);

          window.scrollTo(0, (lastScrollPos + prependItemHeight));
        }
      });

      firstRun = false;
    }
  }).catch(function(err) {
    console.log(err);
  });
}

function getFeeds() { 
  fetch('/api/getFeeds').then(function(res) {
    return res.json();
  }).then(function(data) {
    feeds = data;

    var style = document.createElement('style');
    style.type = 'text/css';

    feeds.forEach(function(feed) {
      if (feed.favicon === '') {
        style.innerHTML = style.innerHTML + `.feed_${feed.id} { padding-left: 0 !important; }`;
      } else {
        style.innerHTML = style.innerHTML + `.feed_${feed.id} { background-image: url('data:image/png;base64, ${feed.favicon}'); }`;
      }

      var newFeed = document.createElement('li');

      newFeed.innerHTML = `<a href="#/feed/${feed.id}">${feed.title}</a>`;

      newFeed.classList.add(`feed_${feed.id}`);

      newFeed.addEventListener('click', function() {
        Array.from(document.querySelectorAll('.active')).forEach((el) => el.classList.remove('active'));
        this.classList.add('active');
        setToggleNav('feed', feed.id, feed.title);
      });

      document.querySelector(`.group.group_${feed.group_id} ul`).append(newFeed);
    });

    document.getElementsByTagName('head')[0].appendChild(style);

    if (window.location.hash === '') {
      window.location.hash = '#/all';
    } else {
      getItems(0);
    }
  }).catch(function(err) {
    console.log(err)
  });
}

fetch('/api/getGroups').then(function(res) {
  return res.json();
}).then(function(data) {
  groups = data;

  groups.forEach(function(groupId) {
    var newGroup = document.createElement('div');

    newGroup.innerHTML = `
        <h3><a href="#/group/${groupId}">${groupId}</a></h3>\
        <ul></ul>`;

    newGroup.classList.add('group', `group_${groupId}`);

    newGroup.querySelector('h3').addEventListener('click', function() {
      Array.from(document.querySelectorAll('.active')).forEach((el) => el.classList.remove('active'));
      this.classList.add('active');
      setToggleNav('group', groupId);
    });

    document.querySelector('.feeds').append(newGroup);
  });

  getFeeds();
}).catch(function(err) {
  console.log(err)
});


setInterval(function() { 
  getItems(lastTimestamp); 
}, 5000);

window.addEventListener('hashchange', hashChange, false);

window.addEventListener('scroll', function() {
  if (window.scrollY === 0) {
    newItemsNum = 0;
    document.querySelector('.counter').innerText = '';
    document.title = docTitle;
  }
});
