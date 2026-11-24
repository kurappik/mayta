/* Только два необязательных улучшения: каталог и корзина без перезагрузки. */
const filters = document.querySelector('[data-live-filter]');
const results = document.getElementById('catalog-results');

if (filters && results) {
  let timer;
  let latestRequest = 0;
  async function refreshCatalog(url) {
    const requestId = ++latestRequest;
    try {
      const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!response.ok) throw new Error('Ошибка поиска');
      const html = await response.text();
      if (requestId === latestRequest) {
        results.innerHTML = html;
        history.replaceState({}, '', url);
      }
    } catch (error) {
      console.warn(error);
    }
  }
  function sendFilters() {
    const url = filters.action + '?' + new URLSearchParams(new FormData(filters)).toString();
    refreshCatalog(url);
  }
  filters.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(sendFilters, 300);
  });
  filters.addEventListener('change', () => {
    clearTimeout(timer);
    sendFilters();
  });
  filters.addEventListener('submit', (event) => {
    event.preventDefault();
    clearTimeout(timer);
    sendFilters();
  });
  results.addEventListener('click', (event) => {
    const link = event.target.closest('.pagination a');
    if (link) {
      event.preventDefault();
      refreshCatalog(link.href);
    }
  });
}

for (const form of document.querySelectorAll('[data-ajax-cart]')) {
  const submitUpdate = async () => {
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) throw new Error('Не удалось изменить количество');
      const data = await response.json();
      const row = form.closest('.cart-row');
      if (data.quantity === 0) row.remove();
      else row.querySelector('[data-line-total]').textContent = data.item_total + ' ₽';
      const total = document.getElementById('cart-total');
      if (total) total.textContent = data.total + ' ₽';
      if (data.count === 0) {
        document.getElementById('cart-list').innerHTML = '<p>Корзина пуста.</p>';
        document.querySelector('.cart-summary .btn')?.remove();
      }
    } catch (error) {
      alert('Не удалось обновить корзину. Попробуйте кнопку «Обновить».');
    }
  };
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    submitUpdate();
  });
  form.querySelector('[name="quantity"]')?.addEventListener('change', submitUpdate);
}
