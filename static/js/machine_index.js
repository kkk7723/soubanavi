"use strict";

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const keywordInput = document.getElementById(
            "machine-keyword"
        );

        const makerSelect = document.getElementById(
            "maker-filter"
        );

        const typeSelect = document.getElementById(
            "machine-type-filter"
        );

        const goukiSelect = document.getElementById(
            "machine-gouki-filter"
        );

        const resetButton = document.getElementById(
            "machine-filter-reset"
        );

        const resultCount = document.getElementById(
            "machine-filter-result"
        );

        const emptyResult = document.getElementById(
            "machine-empty-result"
        );

        const machineCards = Array.from(
            document.querySelectorAll(
                ".machine-card"
            )
        );


        function normalizeText(
            value
        ) {
            return String(
                value || ""
            )
                .normalize(
                    "NFKC"
                )
                .toLowerCase()
                .replace(
                    /\s+/g,
                    ""
                );
        }


        function getSelectedValue(
            element
        ) {
            if (
                !element
            ) {
                return "";
            }

            return normalizeText(
                element.value
            );
        }


        function filterMachines() {

            const keyword =
                normalizeText(
                    keywordInput
                        ? keywordInput.value
                        : ""
                );

            const selectedMaker =
                getSelectedValue(
                    makerSelect
                );

            const selectedType =
                getSelectedValue(
                    typeSelect
                );

            const selectedGouki =
                getSelectedValue(
                    goukiSelect
                );

            let visibleCount = 0;


            machineCards.forEach(
                function (
                    card
                ) {

                    const machineName =
                        normalizeText(
                            card.dataset.machineName
                        );

                    const maker =
                        normalizeText(
                            card.dataset.maker
                        );

                    const machineType =
                        normalizeText(
                            card.dataset.machineType
                        );

                    const machineGouki =
                        normalizeText(
                            card.dataset.machineGouki
                        );


                    const matchesKeyword =
                        (
                            !keyword
                            || machineName.includes(
                                keyword
                            )
                            || maker.includes(
                                keyword
                            )
                        );

                    const matchesMaker =
                        (
                            !selectedMaker
                            || maker
                                === selectedMaker
                        );

                    const matchesType =
                        (
                            !selectedType
                            || machineType
                                === selectedType
                        );

                    const matchesGouki =
                        (
                            !selectedGouki
                            || machineGouki
                                === selectedGouki
                        );


                    const isVisible =
                        (
                            matchesKeyword
                            && matchesMaker
                            && matchesType
                            && matchesGouki
                        );


                    card.hidden =
                        !isVisible;

                    if (
                        isVisible
                    ) {
                        visibleCount += 1;
                    }

                }
            );


            if (
                resultCount
            ) {

                resultCount.textContent =
                    visibleCount.toLocaleString(
                        "ja-JP"
                    )
                    + "件を表示中";

            }


            if (
                emptyResult
            ) {

                emptyResult.hidden =
                    visibleCount !== 0;

            }

        }


        function resetFilters() {

            if (
                keywordInput
            ) {
                keywordInput.value = "";
            }

            if (
                makerSelect
            ) {
                makerSelect.value = "";
            }

            if (
                typeSelect
            ) {
                typeSelect.value = "";
            }

            if (
                goukiSelect
            ) {
                goukiSelect.value = "";
            }

            filterMachines();

            if (
                keywordInput
            ) {
                keywordInput.focus();
            }

        }


        if (
            keywordInput
        ) {

            keywordInput.addEventListener(
                "input",
                debounce(
                    filterMachines,
                    250
                )
            );

        }


        [
            makerSelect,
            typeSelect,
            goukiSelect,
        ].forEach(
            function (
                selectElement
            ) {

                if (
                    selectElement
                ) {

                    selectElement.addEventListener(
                        "change",
                        filterMachines
                    );

                }

            }
        );


        if (
            resetButton
        ) {

            resetButton.addEventListener(
                "click",
                resetFilters
            );

        }


        const params =
            new URLSearchParams(
                window.location.search
            );
        
        const keyword =
            params.get(
                "q"
            );
        
        if (
            keyword
            && keywordInput
        ) {
            keywordInput.value =
                keyword;
        }
        
        if (keyword) {
            filterMachines();
        
        } else if (resultCount) {
            resultCount.textContent =
                machineCards.length.toLocaleString(
                    "ja-JP"
                )
                + "件を表示中";
        }

    }
);