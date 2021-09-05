'use strict';

const itemTypes = { 'group': 'group', 'feed': 'feed' };
const docTitle = document.title;

var lastTimestamp = 0;
var showFeeds = false;
var newItemsCount = 0;
var itemType = 'all';
var itemTypeId = '';
var groups, feeds;


function toggleFeeds() {
  let feedsBlock = document.querySelector('.feeds');

  (showFeeds) ? feedsBlock.classList.remove('show') : feedsBlock.classList.add('show');

  showFeeds = !showFeeds;

  window.scrollTo(0, 0);
}


function setToggleNavInfo(itemType, itemTypeId) {
  let info = document.querySelector('.toggle span.info');

  info.className = 'info';

  switch (itemType) {
    case 'all':
      info.innerHTML = 'all feeds';
      break;

    case 'group':
      info.innerHTML = `${itemTypeId}`;
      break;

    case 'feed':
      info.innerHTML = `${feeds.find(feed => feed.id === itemTypeId).title}`;
      info.classList.add(`feed_${itemTypeId}`);
      break;
  }
}


function setNewItemsCounter(newItems) {
  newItemsCount += newItems;

  let counterValue = (newItemsCount > 99) ? '99+' : newItemsCounter;

  document.querySelector('.counter').innerText = counterValue;
  document.title = `${docTitle} (${counterValue})`;
}


function formatDate(date) {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric', hour12: false
  }).format(new Date(date*1000));
}


function getItems(since) {
  let fetchUrl = `/api/getItems?since=${since}`;

  if (itemType !== 'all')
    fetchUrl = `${fetchUrl}&${itemTypes[itemType]}_id=${itemTypeId}`;

  fetch(fetchUrl).then(function(res) {
    return res.json();
  }).then(function(data) {
    let items = data;
    let lastScrollPos = window.scrollY;
    let itemsHtml = document.querySelector('.items');
    let itemsHtmlStyle = window.getComputedStyle(itemsHtml);
    let itemsHtmlHeightBefore = itemsHtml.offsetHeight + parseInt(itemsHtmlStyle.marginTop) + parseInt(itemsHtmlStyle.marginBottom);

    if (since === 0)
      itemsHtml.innerHTML = '';

    if (items.length > 0) {
      console.log(items.length);
      lastTimestamp = items[0].added;

      if (since > 0)
        setNewItemsCounter(items.length);

      Array.from(document.querySelectorAll('article')).forEach((el) => el.classList.remove('new'));

      itemsHtml.innerHTML =
        `${items.map(item =>
          `<article class="new">
             <h5 class="feed_${item.feed}">${feeds.find(feed => feed.id === item.feed).title}:</h5>
             <h4><a href="${item.link}" target="_blank">${item.title}</a></h4>
             <h6>${formatDate(item.published)}</h6>
             <p>${item.description}</p>
          </article>`
        ).join('')}` + itemsHtml.innerHTML;

      if (since > 0 && window.scrollY > 0) {
        let itemsHtmlHeightAfter = itemsHtml.offsetHeight + parseInt(itemsHtmlStyle.marginTop) + parseInt(itemsHtmlStyle.marginBottom);
        let itemsHtmlHeightDiff = itemsHtmlHeightAfter - itemsHtmlHeightBefore;

        window.scrollTo(0, (lastScrollPos + itemsHtmlHeightDiff));
      }
    }
  }).catch(function(err) {
    console.log(err);
  });
}


function showItems(newItemType, newItemTypeId) {
  itemType = newItemType;
  itemTypeId = newItemTypeId;
  newItemsCount = 0;

  Array.from(document.querySelectorAll('.active')).forEach((el) => el.classList.remove('active'));

  document.querySelector((itemType === 'all') ? '.group.all' : `.${itemType}.${itemType}_${itemTypeId}`).classList.add('active');
  document.querySelector('.feeds').classList.remove('show');
  window.scrollTo(0, 0);

  setToggleNavInfo(itemType, itemTypeId);
  getItems(0);
}


if (window.location.hash) {
  let params = window.location.hash.substring(1).split('/');
  
  itemType = params[1] || 'all';
  itemTypeId = params[2] || '';
} else {
  window.location.hash = '#/all';
}

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
          `.feed_${feed.id} { padding-left: 20px; background-image: url('data:image/png;base64, ${feed.favicon}'); }`
        ).join('')}
      </style>`;

    document.querySelector('.feeds').innerHTML += 
      `${groups.map(groupId =>
        `<div class="group group_${groupId}">
          <h3 onclick="showItems('group', '${groupId}');"><a href="#/group/${groupId}">${groupId}</a></h3>
          <ul>
          ${feeds.filter(feed => feed.group_id === groupId).map(feed =>
            `<li class="feed feed_${feed.id}" onclick="showItems('feed', '${feed.id}');"><a href="#/feed/${feed.id}">${feed.title}</li>`     
          ).join('')}
          </ul>
        </div>`
      ).join('')}`;

    showItems(itemType, itemTypeId);
  }).catch(function(err) {
    console.log(err)
  });
}).catch(function(err) {
  console.log(err)
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
