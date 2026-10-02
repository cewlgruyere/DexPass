(function () {
    function getRow(select) {
        return select.closest(".inline-related") || select.closest("tr");
    }

    function toggle(select) {
        var row = getRow(select);
        if (!row) return;

        var selected = select.value;

        // Every dynamically generated reward field has "__" in its name.
        row.querySelectorAll('[name*="__"]').forEach(function (input) {
            var field = input.closest(".form-row") ||
                        input.closest(".field-box") ||
                        input.closest("td") ||
                        input.parentElement;

            if (!field) return;

            var match = input.name.match(/__([^_]+)$/);
            if (!match) return;

            // Find the reward model portion before "__".
            var model = input.name.split("__")[0];
            model = model.substring(model.lastIndexOf("-") + 1);

            field.style.display = (model === selected) ? "" : "none";
        });
    }

    function init(root) {
        (root || document)
            .querySelectorAll('select[name$="-reward_type"]')
            .forEach(function (select) {
                toggle(select);

                if (!select.dataset.rewardToggleBound) {
                    select.dataset.rewardToggleBound = "1";

                    select.addEventListener("change", function () {
                        toggle(select);
                    });
                }
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        init(document);
    });

    document.addEventListener("formset:added", function (event) {
        init(event.target);
    });
})();