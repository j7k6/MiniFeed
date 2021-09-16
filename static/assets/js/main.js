'use strict';

const itemTypes = { 'group': 'group', 'feed': 'feed' };
const docTitle = document.title;
const itemsHtml = document.querySelector('.items');

var lastTimestamp = 0;
var showFeeds = false;
var newItemsCount = 0;

var darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches ? true : false;

var groups, feeds;
var params, itemType, itemTypeId;


function setMode(mode) {
  darkMode = mode;

  if (darkMode) {
    document.body.classList.add('dark');
    document.querySelector('.mode').innerHTML = '&#9788;';
  } else {
    document.body.classList.remove('dark');
    document.querySelector('.mode').innerHTML = '&#9790;';
  }
}


function getParams() {
  params = window.location.hash.substring(1).split('/');
  itemType = params[1] || 'all';
  itemTypeId = params[2] || '';
}


function toggleFeeds() {
  showFeeds = !showFeeds;

  if (showFeeds) {
    document.querySelector('.feeds').classList.add('show');
    document.querySelector('.menu').innerHTML = '&#215;';
  } else {
    document.querySelector('.feeds').classList.remove('show');
    document.querySelector('.menu').innerHTML = '&#9776;';
  }

  window.scrollTo(0, 0);
}


function setNavInfo(itemType, itemTypeId) {
  let info = document.querySelector('.info');

  info.className = 'info';

  switch (itemType) {
    case 'all':
      info.innerHTML = 'all feeds';
      break;

    case 'group':
      info.innerHTML = `${itemTypeId}`;
      break;

    case 'feed':
      let feed = feeds.find(feed => feed.id === itemTypeId)

      info.innerHTML = feed.title;
      info.classList.add(`feed_${itemTypeId}`);

      if (feed.favicon !== '') info.classList.add('favicon');
      break;
  }
}


function setItemCounter(newItems) {
  let counterValue;

  newItemsCount += newItems;

  counterValue = (newItemsCount > 99) ? '99+' : newItemsCount;
  counterValue = (newItemsCount > 0) ? counterValue : '';

  document.querySelector('.counter').innerText = counterValue;
  document.title = `${docTitle}${(newItemsCount > 0) ? ` (${newItemsCount})` : ''}`;
}


function formatDate(date) {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric', hour12: false
  }).format(new Date(date*1000));
}


function showItems(newItemType, newItemTypeId) {
  itemType = newItemType;
  itemTypeId = newItemTypeId;
  newItemsCount = 0;
  showFeeds = true;
  toggleFeeds();

  Array.from(document.querySelectorAll('.active')).forEach((el) => el.classList.remove('active'));

  document.querySelector((itemType === 'all') ? '.group.all' : `.${itemType}.${itemType}_${itemTypeId}`).classList.add('active');
  document.querySelector('.feeds').classList.remove('show');
  window.scrollTo(0, 0);

  setItemCounter(0)
  setNavInfo(itemType, itemTypeId);
  getItems(0);
}


function getItems(since) {
  let fetchUrl = `/api/getItems?since=${since}`;

  if (itemType !== 'all')
    fetchUrl = `${fetchUrl}&${itemTypes[itemType]}_id=${itemTypeId}`;
  if (since === 0)
    itemsHtml.innerHTML = '';

  fetch(fetchUrl).then(function(res) {
    return res.json();
  }).then(function(data) {
    if (data.length > 0)
      renderItems(data, since);
  }).catch(function(err) {
    console.log(err);
  });
}


function renderItems(items, since=null) {
  Array.from(document.querySelectorAll('article')).forEach((el) => el.classList.remove('new'));

  if (items.length > 0) {
    console.log(items.length);

    let newItemsHtml =
      `${Array.from(items).sort((a, b) => b.published - a.published).map(item =>
        `<article class="new" id="${item.id}">
           <h5 class="feed_${item.feed} favicon">${feeds.find(feed => feed.id === item.feed).title}:</h5>
           <h4><a href="${item.link}" target="_blank">${item.title}</a></h4>
           <h6>${formatDate(item.published)}</h6>
           <p>${item.description}</p>
        </article>`
      ).join('')}`;

    if (since !== null) {
      let lastScrollPos = window.scrollY;
      let itemsHtmlStyle = window.getComputedStyle(itemsHtml);
      let itemsHtmlHeightBefore = itemsHtml.offsetHeight + parseInt(itemsHtmlStyle.marginTop) + parseInt(itemsHtmlStyle.marginBottom);

      lastTimestamp = items[0].added;

      if (since === 0)
        itemsHtml.innerHTML = '';

      itemsHtml.innerHTML = newItemsHtml + itemsHtml.innerHTML;

      if (since > 0) {
        setItemCounter(items.length);

        if (window.scrollY > 0) {
          let itemsHtmlHeightAfter = itemsHtml.offsetHeight + parseInt(itemsHtmlStyle.marginTop) + parseInt(itemsHtmlStyle.marginBottom);
          let itemsHtmlHeightDiff = itemsHtmlHeightAfter - itemsHtmlHeightBefore;

          window.scrollTo(0, (lastScrollPos + itemsHtmlHeightDiff));
        }
      }
    } else {
      itemsHtml.innerHTML = itemsHtml.innerHTML + newItemsHtml;
    }
  }
}


setMode(darkMode);

if (!window.location.hash)
  window.location.hash = '#/all';

fetch('/api/getGroups').then(function(res) {
  return res.json();
}).then(function(data) {
  groups = data;

  fetch('/api/getFeeds').then(function(res) {
    return res.json();
  }).then(function(data) {
    feeds = data;

    document.querySelector('head').innerHTML +=
      `<style type="text/css">
        ${feeds.filter(feed => feed.favicon !== '').map(feed =>
          `.feed_${feed.id} { padding-left: 1.5rem !important; background-image: url('data:image/png;base64, ${feed.favicon}'); }`
        ).join('')}
      </style>`;

    document.querySelector('.feeds').innerHTML += 
      `${groups.map(groupId =>
        `<div class="group group_${groupId}">
          <h3><a href="#/group/${groupId}">${groupId}</a></h3>
          <ul>
          ${feeds.filter(feed => feed.group === groupId).map(feed =>
            `<li class="feed favicon feed_${feed.id}"><a href="#/feed/${feed.id}">${feed.title}</li>`     
          ).join('')}
          </ul>
        </div>`
      ).join('')}`;

    getParams();
    showItems(itemType, itemTypeId);
  }).catch(function(err) {
    console.log(err);
  });
}).catch(function(err) {
  console.log(err);
});

setInterval(function() { 
  getItems(lastTimestamp); 
}, 5000);

window.addEventListener('scroll', function() {
  if (window.scrollY === 0) {
    newItemsCount = 0;

    document.querySelector('.counter').innerText = '';
    document.title = docTitle;
  }
});

window.addEventListener('hashchange', function() {
  getParams();

  if (feeds)
    showItems(itemType, itemTypeId);
});
