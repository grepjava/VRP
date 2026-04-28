<script>
  import { createEventDispatcher } from 'svelte'
  import { generateDemo } from './api.js'

  const dispatch = createEventDispatcher()

  export let techCount = 0
  export let orderCount = 0

  let city = 'Kuala Lumpur'
  let numOrders = 15
  let numTechnicians = 4
  let loading = false
  let error = null
  let confirming = false

  $: hasExistingData = techCount > 0 || orderCount > 0
  $: city, numOrders, numTechnicians, (confirming = false)

  // Autocomplete state
  let suggestions = []
  let suggestionsLoading = false
  let activeIdx = -1
  let _debounceTimer = null
  let _suppressSearch = false  // set true after selection to avoid re-triggering

  function onCityInput() {
    if (_suppressSearch) { _suppressSearch = false; return }
    clearTimeout(_debounceTimer)
    activeIdx = -1
    if (city.trim().length < 2) { suggestions = []; return }
    _debounceTimer = setTimeout(fetchSuggestions, 300)
  }

  async function fetchSuggestions() {
    suggestionsLoading = true
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(city)}&format=json&limit=6&addressdetails=1`,
        { headers: { 'User-Agent': 'cuopt-vrp-demo/1.0' } }
      )
      const data = await res.json()
      suggestions = data.map(item => {
        const addr = item.address || {}
        const name = addr.city || addr.town || addr.village || addr.county ||
                     addr.state_district || item.display_name.split(',')[0]
        const country = addr.country || ''
        const state = addr.state || addr.region || ''
        const sub = [state, country].filter(Boolean).join(', ')
        return { name, sub, full: item.display_name, type: item.type }
      })
    } catch {
      suggestions = []
    }
    suggestionsLoading = false
  }

  function selectSuggestion(s) {
    _suppressSearch = true
    city = s.name
    suggestions = []
    activeIdx = -1
  }

  function closeSuggestions() {
    // Delay so mousedown on a suggestion fires before blur clears the list
    setTimeout(() => { suggestions = []; activeIdx = -1 }, 150)
  }

  function onInputKeydown(e) {
    if (suggestions.length) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        activeIdx = Math.min(activeIdx + 1, suggestions.length - 1)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        activeIdx = Math.max(activeIdx - 1, -1)
      } else if (e.key === 'Enter' && activeIdx >= 0) {
        e.preventDefault()
        selectSuggestion(suggestions[activeIdx])
        return
      } else if (e.key === 'Escape') {
        suggestions = []
        return
      }
    }
  }

  function onWindowKeydown(e) {
    if (e.key === 'Escape' && !suggestions.length) dispatch('close')
    if (e.key === 'Enter' && !loading && !suggestions.length) handleGenerate()
  }

  async function handleGenerate() {
    if (!city.trim()) return
    if (hasExistingData && !confirming) { confirming = true; return }
    confirming = false
    loading = true
    error = null
    try {
      const data = await generateDemo(city.trim(), numOrders, numTechnicians)
      dispatch('generate', data)
    } catch (e) {
      error = e.message
    }
    loading = false
  }

  function cancelConfirm() { confirming = false }
</script>

<svelte:window on:keydown={onWindowKeydown} />

<!-- svelte-ignore a11y-click-events-have-key-events -->
<div class="backdrop" on:click={() => dispatch('close')} role="presentation"></div>

<div class="panel" role="dialog" aria-label="Generate Demo Data">
  <div class="panel-header">
    <span class="panel-title">Generate Demo Data</span>
    <button class="close-btn" on:click={() => dispatch('close')}>✕</button>
  </div>

  <div class="panel-body">
    <div class="field">
      <label class="field-label" for="demo-city">City or Area</label>
      <div class="city-wrap">
        <input
          id="demo-city"
          type="text"
          class="text-input"
          class:open={suggestions.length > 0}
          bind:value={city}
          on:input={onCityInput}
          on:keydown={onInputKeydown}
          on:blur={closeSuggestions}
          placeholder="e.g. Singapore, London, Tokyo"
          disabled={loading}
          autocomplete="off"
        />
        {#if suggestionsLoading}
          <span class="search-spinner"></span>
        {/if}
        {#if suggestions.length > 0}
          <ul class="suggestions" role="listbox">
            {#each suggestions as s, i}
              <!-- svelte-ignore a11y-click-events-have-key-events -->
              <li
                class="suggestion"
                class:active={i === activeIdx}
                role="option"
                aria-selected={i === activeIdx}
                on:mousedown={() => selectSuggestion(s)}
              >
                <span class="sug-name">{s.name}</span>
                {#if s.sub}<span class="sug-sub">{s.sub}</span>{/if}
                <span class="sug-type">{s.type}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>

    <div class="field">
      <div class="slider-header">
        <label class="field-label" for="demo-orders">Work Orders</label>
        <span class="slider-value">{numOrders}</span>
      </div>
      <input id="demo-orders" type="range" class="slider" bind:value={numOrders} min="5" max="50" step="1" disabled={loading} />
      <div class="slider-ends"><span>5</span><span>50</span></div>
    </div>

    <div class="field">
      <div class="slider-header">
        <label class="field-label" for="demo-techs">Technicians</label>
        <span class="slider-value">{numTechnicians}</span>
      </div>
      <input id="demo-techs" type="range" class="slider" bind:value={numTechnicians} min="1" max="15" step="1" disabled={loading} />
      <div class="slider-ends"><span>1</span><span>15</span></div>
    </div>

    {#if error}
      <div class="error-msg">⚠ {error}</div>
    {/if}
  </div>

  <div class="panel-footer">
    {#if confirming}
      <div class="confirm-row">
        <span class="confirm-msg">Replace {techCount} technicians &amp; {orderCount} work orders?</span>
        <div class="confirm-btns">
          <button class="cancel-btn" on:click={cancelConfirm}>Cancel</button>
          <button class="replace-btn" on:click={handleGenerate}>Replace</button>
        </div>
      </div>
    {:else}
      <button class="cancel-btn" on:click={() => dispatch('close')} disabled={loading}>Cancel</button>
      <button class="generate-btn" on:click={handleGenerate} disabled={loading || !city.trim()}>
        {#if loading}
          <span class="spinner"></span> Generating…
        {:else}
          ⚡ Generate
        {/if}
      </button>
    {/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 2000;
  }

  .panel {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 340px; background: #1a1d2e; border: 1px solid #2d3250;
    border-radius: 12px; z-index: 2001; display: flex; flex-direction: column;
    box-shadow: 0 16px 48px rgba(0,0,0,0.5);
  }

  .panel-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; border-bottom: 1px solid #2d3250;
  }
  .panel-title { font-size: 14px; font-weight: 700; color: #e0e6f0; }
  .close-btn {
    background: none; border: none; color: #8892b0; font-size: 16px;
    cursor: pointer; padding: 2px 6px; border-radius: 4px;
  }
  .close-btn:hover { color: #e0e6f0; background: #2d3250; }

  .panel-body { padding: 16px; display: flex; flex-direction: column; gap: 18px; }

  .field { display: flex; flex-direction: column; gap: 6px; }
  .field-label { font-size: 12px; font-weight: 600; color: #8892b0; text-transform: uppercase; letter-spacing: 0.05em; }

  /* City input + dropdown wrapper */
  .city-wrap { position: relative; }

  .text-input {
    width: 100%; box-sizing: border-box;
    padding: 9px 12px; background: #232640; border: 1px solid #2d3250;
    border-radius: 8px; color: #e0e6f0; font-size: 14px;
  }
  .text-input:focus { border-color: #6c63ff; outline: none; }
  .text-input.open { border-bottom-left-radius: 0; border-bottom-right-radius: 0; border-color: #6c63ff; }
  .text-input:disabled { opacity: 0.5; }

  /* Spinner inside input */
  .search-spinner {
    position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
    width: 14px; height: 14px; border: 2px solid #2d3250;
    border-top-color: #6c63ff; border-radius: 50%;
    animation: spin 0.7s linear infinite; pointer-events: none;
  }

  /* Suggestions dropdown */
  .suggestions {
    position: absolute; left: 0; right: 0; top: 100%;
    background: #232640; border: 1px solid #6c63ff; border-top: none;
    border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
    z-index: 10; margin: 0; padding: 4px 0; list-style: none;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4); max-height: 220px; overflow-y: auto;
  }

  .suggestion {
    display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
    padding: 8px 12px; cursor: pointer;
  }
  .suggestion:hover, .suggestion.active { background: #2a2e55; }

  .sug-name { font-size: 13px; color: #e0e6f0; font-weight: 600; }
  .sug-sub { font-size: 11px; color: #8892b0; flex: 1; }
  .sug-type {
    font-size: 10px; color: #6c63ff; background: rgba(108,99,255,0.12);
    padding: 1px 5px; border-radius: 4px; font-weight: 600; white-space: nowrap;
    margin-left: auto;
  }

  .slider-header { display: flex; align-items: center; justify-content: space-between; }
  .slider-value { font-size: 20px; font-weight: 700; color: #6c63ff; font-variant-numeric: tabular-nums; }

  .slider { width: 100%; accent-color: #6c63ff; cursor: pointer; height: 4px; }
  .slider:disabled { opacity: 0.5; cursor: not-allowed; }

  .slider-ends { display: flex; justify-content: space-between; font-size: 11px; color: #556; }

  .error-msg {
    background: rgba(192,57,43,0.15); border: 1px solid rgba(192,57,43,0.4);
    border-radius: 8px; padding: 9px 12px; font-size: 12px; color: #e74c3c;
  }

  .panel-footer {
    display: flex; justify-content: flex-end; gap: 10px;
    padding: 14px 16px; border-top: 1px solid #2d3250;
  }

  .confirm-row {
    display: flex; flex-direction: column; gap: 10px; width: 100%;
  }
  .confirm-msg { font-size: 12px; color: #ffd60a; text-align: center; }
  .confirm-btns { display: flex; justify-content: flex-end; gap: 10px; }

  .replace-btn {
    padding: 9px 18px; background: #c0392b; color: #fff;
    border-radius: 8px; font-size: 13px; font-weight: 700; border: none;
  }
  .replace-btn:hover { background: #a93226; }

  .cancel-btn {
    padding: 9px 18px; background: #232640; color: #8892b0;
    border: 1px solid #2d3250; border-radius: 8px; font-size: 13px; font-weight: 600;
  }
  .cancel-btn:hover:not(:disabled) { color: #e0e6f0; border-color: #6c63ff; }

  .generate-btn {
    padding: 9px 22px; background: #6c63ff; color: #fff;
    border-radius: 8px; font-size: 14px; font-weight: 700;
    display: flex; align-items: center; gap: 8px;
  }
  .generate-btn:hover:not(:disabled) { background: #5a52d5; }
  .generate-btn:disabled { opacity: 0.6; cursor: not-allowed; }

  .spinner {
    width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff; border-radius: 50%;
    animation: spin 0.7s linear infinite; flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
