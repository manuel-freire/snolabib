"use strict"
{
    function all(sel) { return document.querySelectorAll(sel);}
    function one(sel) { return document.querySelector(sel);}
    function inc(map, key) {
        map.set(key, map.has(key) ? map.get(key) + 1 : 1); 
    }
    function getz(map, key, z) {
        return map.has(key) ? map.get(key) : z;
    }    

    const filters = {
        author: new Set(),
        year: new Set(),
        venue: new Set(),
    };

    const counts = {
        author: new Map(),
        year: new Map(),
        venue: new Map(),
    };

    // refilter based on current filters. Also updates total counts
    function do_filter() {
        console.log("filtering: authors=",...filters.author, "years=",...filters.year, "venues=",...filters.venue)
        const years = new Map();
        const authors = new Map();
        const venues = new Map();
        let total = 0;

        all("li.bibitem").forEach(i => {
            const yearOk = filters.year.size === 0 || filters.year.has(i.dataset.year)
            const venueOk = filters.venue.size === 0 || filters.venue.has(i.dataset.venue)
            let authOk = filters.author.size === 0;
            if ( ! authOk) {
                authOk = true;
                for (let a of filters.author.values()) {
                    if (i.dataset.authors.indexOf(a) === -1) {
                        authOk = false;
                    }
                }
            }
            if (yearOk && authOk && venueOk) {
                i.style.display = '';
                inc(years, i.dataset.year);
                for (let a of i.dataset.authors.split(",")) {
                    inc(authors, a);
                }
                inc(venues, i.dataset.venue);
                total ++;
            } else {
                i.style.display = 'none';
            }
        })

        // update counts, hide if filtered && count == 0
        const filtered = ((filters.year.size + filters.author.size + filters.venue.size) > 0);
        all("button.yfilter").forEach(b => {
            const k = b.dataset.year;
            b.style.display = (filtered && getz(years, k, 0)==0) ? 'none' : '';
            b.querySelector(".bibcount").textContent = 
                `(${filtered ? getz(years, k, 0) + "/": ""}${counts.year.get(k)})`;
        });
        all("button.afilter").forEach(b => {
            const k = b.dataset.author;
            b.style.display = (filtered && getz(authors, k, 0)==0) ? 'none' : '';
            b.querySelector(".bibcount").textContent = 
                `(${filtered ? getz(authors, k, 0) + "/": ""}${counts.author.get(k)})`;
        });
        all("button.vfilter").forEach(b => {
            const k = b.dataset.venue;
            b.style.display = (filtered && getz(venues, k, 0)==0) ? 'none' : '';
            b.querySelector(".bibcount").textContent = 
                `(${filtered ? getz(venues, k, 0) + "/": ""}${counts.venue.get(k)})`;
        }); 

        // update publication count
        one("h2.pubcount").textContent = `Mostrando ${total} publicaci${total==1?"ón":"ones"}`;
    }

    // update filtering buttons/information after click, and finally refilter
    function filter_click(event) {
        const target = event.target.nodeName.toLowerCase() === 'span' ? 
            event.target.parentNode : event.target;
        let element = undefined;
        let filter = undefined;
        if (target.classList.contains("yfilter")) {
            element = target.dataset.year;
            filter = filters.year;
        } else if (target.classList.contains("afilter")) {
            element = target.dataset.author;
            filter = filters.author;
        } else if (target.classList.contains("vfilter")) {
            element = target.dataset.venue;
            filter = filters.venue;
        }

        if (element !== undefined) {
            if (filter.has(element)) {
                filter.delete(element);
                target.classList.remove("fset")
            } else {
                filter.add(element);
                target.classList.add("fset")
            } 
        } else {
            console.log("Ignoring stray click on: ", target)
        }
        do_filter()
    }

    // generate filter buttons for authors, ordered by publication counts
    function populate_authors(authors_div) {
        console.log("Populating authors...")
        const unsorted = []
        for (let [k, a] of Object.entries(authors)) {
            let n = 0;
            all("li.bibitem").forEach(
                i => n+=i.dataset.authors.indexOf(a.id)>=0?1:0);
            counts.author.set(a.id, n)
            unsorted.push({n, a})
        }
        unsorted.sort((a, b) => b.n - a.n)        
        authors_div.insertAdjacentHTML("beforeend", 
            unsorted.map(o => 
                `<button class="afilter" data-author=${o.a.id}>${o.a.full} <span class="bibcount"></span></button>`)
                .join(' '));
        all("button.afilter").forEach(o => o.addEventListener("click", filter_click))
    }

    // generate filter buttons for years with publications, ordered by publication counts
    function populate_years(years_div) {
        console.log("Populating years...")
        all("li.bibitem").forEach(i => inc(counts.year, i.dataset.year));
        const unsorted = []
        for (let [y, n] of counts.year.entries())
            unsorted.push({y, n})
        unsorted.sort((a, b) => a.y - b.y)
        years_div.insertAdjacentHTML("beforeend",
            unsorted.map(o =>              
                `<button class="yfilter" data-year=${o.y}>${o.y} <span class="bibcount"></span></button>`)
            .join(' '));
        all("button.yfilter").forEach(o => o.addEventListener("click", filter_click))
    }

    // generate filter buttons for venues with publications, ordered by publication counts
    function populate_venues(venues_div) {
        console.log("Populating venues...")
        all("li.bibitem").forEach(i => inc(counts.venue, i.dataset.venue));
        const unsorted = []
        for (let [v, n] of counts.venue.entries())
            unsorted.push({v, n})
        unsorted.sort((a, b) => b.n - a.n)
        venues_div.insertAdjacentHTML("beforeend",
            unsorted.map(o =>              
                `<button class="vfilter" data-venue=${o.v}>${o.v} <span class="bibcount"></span></button>`)
            .join(' '));
        all("button.vfilter").forEach(o => o.addEventListener("click", filter_click))
    }    

    // populates filters when page is fully loaded
    window.addEventListener("load", () => {
        populate_authors(one("div.authors"))
        populate_years(one("div.years"))
        populate_venues(one("div.venues"))
        do_filter()
    })
}