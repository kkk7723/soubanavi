"use strict";


/**
 * 機種詳細ページ用JavaScript
 *
 * 主な処理:
 * ・価格履歴JSONの読み込み
 * ・価格推移グラフの生成
 * ・価格表示の円表記
 */


/**
 * DOMの読み込み完了後に処理を開始する。
 */
document.addEventListener(
    "DOMContentLoaded",
    function () {
        initializePriceHistoryChart();
        initializeShareUrlCopy();
    }
);


/**
 * 価格推移グラフを初期化する。
 */
function initializePriceHistoryChart() {
    const dataElement = document.getElementById(
        "price-history-data"
    );

    const canvasElement = document.getElementById(
        "price-history-chart"
    );

    /*
     * 価格履歴JSONまたはcanvasがないページでは
     * 何も実行しない。
     */
    if (!dataElement || !canvasElement) {
        return;
    }

    /*
     * Chart.jsが読み込まれていない場合。
     */
    if (typeof Chart === "undefined") {
        console.error(
            "Chart.jsが読み込まれていません。"
        );

        return;
    }

    const priceHistory = parsePriceHistoryData(
        dataElement
    );

    /*
     * 2日分未満の場合はグラフを生成しない。
     */
    if (
        !Array.isArray(priceHistory)
        || priceHistory.length < 2
    ) {
        return;
    }

    const chartData = buildPriceHistoryChartData(
        priceHistory
    );

    const chartOptions =
        buildPriceHistoryChartOptions();

    const chartContext = canvasElement.getContext(
        "2d"
    );

    if (!chartContext) {
        console.error(
            "価格推移グラフの描画領域を取得できません。"
        );

        return;
    }

    new Chart(
        chartContext,
        {
            type: "line",
            data: chartData,
            options: chartOptions,
        }
    );
}


/**
 * HTML内に埋め込まれた価格履歴JSONを取得する。
 *
 * @param {HTMLElement} dataElement
 * @returns {Array<Object>}
 */
function parsePriceHistoryData(
    dataElement
) {
    try {
        const jsonText =
            dataElement.textContent.trim();

        if (!jsonText) {
            return [];
        }

        const parsedData = JSON.parse(
            jsonText
        );

        if (!Array.isArray(parsedData)) {
            console.error(
                "価格履歴データが配列ではありません。"
            );

            return [];
        }

        return parsedData;

    } catch (error) {
        console.error(
            "価格履歴JSONの解析に失敗しました。",
            error
        );

        return [];
    }
}


/**
 * Chart.js用のデータを生成する。
 *
 * @param {Array<Object>} priceHistory
 * @returns {Object}
 */
function buildPriceHistoryChartData(
    priceHistory
) {
    const labels = priceHistory.map(
        function (history) {
            return formatRecordDate(
                history.record_date
            );
        }
    );

    const minimumPrices = priceHistory.map(
        function (history) {
            return normalizeChartPrice(
                history.min_price
            );
        }
    );

    const averagePrices = priceHistory.map(
        function (history) {
            return normalizeChartPrice(
                history.avg_price
            );
        }
    );

    const maximumPrices = priceHistory.map(
        function (history) {
            return normalizeChartPrice(
                history.max_price
            );
        }
    );

    return {
        labels: labels,

        datasets: [
            {
                label: "最安価格",
                data: minimumPrices,
                borderColor: "#2563eb",
                backgroundColor:
                    "rgba(37, 99, 235, 0.12)",
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 6,
                pointHitRadius: 12,
                tension: 0.25,
                fill: false,
                spanGaps: true,
            },
            {
                label: "平均価格",
                data: averagePrices,
                borderColor: "#16a34a",
                backgroundColor:
                    "rgba(22, 163, 74, 0.12)",
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 6,
                pointHitRadius: 12,
                tension: 0.25,
                fill: false,
                spanGaps: true,
            },
            {
                label: "最高価格",
                data: maximumPrices,
                borderColor: "#dc2626",
                backgroundColor:
                    "rgba(220, 38, 38, 0.12)",
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 6,
                pointHitRadius: 12,
                tension: 0.25,
                fill: false,
                spanGaps: true,
            },
        ],
    };
}


/**
 * Chart.js用のオプションを生成する。
 *
 * @returns {Object}
 */
function buildPriceHistoryChartOptions() {
    return {
        responsive: true,

        maintainAspectRatio: false,

        interaction: {
            mode: "index",
            intersect: false,
        },

        plugins: {
            legend: {
                display: true,
                position: "top",

                labels: {
                    usePointStyle: true,
                    boxWidth: 10,
                    boxHeight: 10,
                    padding: 16,
                },
            },

            tooltip: {
                enabled: true,

                callbacks: {
                    title: function (
                        tooltipItems
                    ) {
                        if (
                            !tooltipItems
                            || tooltipItems.length === 0
                        ) {
                            return "";
                        }

                        return tooltipItems[0].label;
                    },

                    label: function (
                        context
                    ) {
                        const datasetLabel =
                            context.dataset.label
                            || "";

                        const value =
                            context.parsed.y;

                        if (
                            value === null
                            || value === undefined
                        ) {
                            return (
                                datasetLabel
                                + ": データなし"
                            );
                        }

                        return (
                            datasetLabel
                            + ": "
                            + formatYen(value)
                        );
                    },
                },
            },
        },

        scales: {
            x: {
                display: true,

                title: {
                    display: false,
                },

                grid: {
                    display: false,
                },

                ticks: {
                    autoSkip: true,
                    maxRotation: 0,
                    minRotation: 0,
                    maxTicksLimit: 10,
                },
            },

            y: {
                display: true,
                beginAtZero: false,

                title: {
                    display: true,
                    text: "価格",
                },

                ticks: {
                    callback: function (
                        value
                    ) {
                        return formatCompactYen(
                            value
                        );
                    },
                },
            },
        },
    };
}


/**
 * 価格をChart.jsで扱える数値へ変換する。
 *
 * @param {*} value
 * @returns {number|null}
 */
function normalizeChartPrice(
    value
) {
    if (
        value === null
        || value === undefined
        || value === ""
    ) {
        return null;
    }

    const normalizedValue = String(
        value
    )
        .replace(/,/g, "")
        .replace(/円/g, "")
        .trim();

    const numericValue = Number(
        normalizedValue
    );

    if (!Number.isFinite(numericValue)) {
        return null;
    }

    return numericValue;
}


/**
 * 日付をグラフ表示用に整形する。
 *
 * 例:
 * 2026-07-19
 * ↓
 * 7/19
 *
 * @param {*} value
 * @returns {string}
 */
function formatRecordDate(
    value
) {
    if (!value) {
        return "";
    }

    const dateText = String(
        value
    ).trim();

    const dateMatch = dateText.match(
        /^(\d{4})-(\d{1,2})-(\d{1,2})/
    );

    if (!dateMatch) {
        return dateText;
    }

    const month = Number(
        dateMatch[2]
    );

    const day = Number(
        dateMatch[3]
    );

    return `${month}/${day}`;
}


/**
 * 金額を円表記へ整形する。
 *
 * 例:
 * 123456
 * ↓
 * 123,456円
 *
 * @param {*} value
 * @returns {string}
 */
function formatYen(
    value
) {
    const numericValue = Number(
        value
    );

    if (!Number.isFinite(numericValue)) {
        return "-";
    }

    return (
        Math.round(
            numericValue
        ).toLocaleString(
            "ja-JP"
        )
        + "円"
    );
}


/**
 * Y軸用の短縮金額表記。
 *
 * 例:
 * 50000
 * ↓
 * 5万円
 *
 * 125000
 * ↓
 * 12.5万円
 *
 * @param {*} value
 * @returns {string}
 */
function formatCompactYen(
    value
) {
    const numericValue = Number(
        value
    );

    if (!Number.isFinite(numericValue)) {
        return "";
    }

    if (
        Math.abs(numericValue) >= 10000
    ) {
        const tenThousandValue =
            numericValue / 10000;

        const formattedValue =
            Number.isInteger(
                tenThousandValue
            )
                ? tenThousandValue.toFixed(0)
                : tenThousandValue.toFixed(1);

        return (
            formattedValue
            + "万円"
        );
    }

    return (
        Math.round(
            numericValue
        ).toLocaleString(
            "ja-JP"
        )
        + "円"
    );
}

/**
 * SNSシェア欄のURLコピーボタンを初期化する。
 */
function initializeShareUrlCopy() {
    const copyButtons = document.querySelectorAll(
        ".share-button-copy"
    );

    /*
     * URLコピーボタンがないページでは
     * 何も実行しない。
     */
    if (copyButtons.length === 0) {
        return;
    }

    copyButtons.forEach(
        function (copyButton) {
            copyButton.addEventListener(
                "click",
                function () {
                    copyShareUrl(
                        copyButton
                    );
                }
            );
        }
    );
}


/**
 * シェアURLをクリップボードへコピーする。
 *
 * @param {HTMLButtonElement} copyButton
 */
async function copyShareUrl(
    copyButton
) {
    const shareUrl = String(
        copyButton.dataset.shareUrl
        || ""
    ).trim();

    if (!shareUrl) {
        showShareCopyMessage(
            copyButton,
            "コピーするURLがありません。",
            true
        );

        return;
    }

    /*
     * 連続クリックを防止する。
     */
    copyButton.disabled = true;

    try {
        await writeTextToClipboard(
            shareUrl
        );

        showShareCopyMessage(
            copyButton,
            "ページURLをコピーしました。",
            false
        );

        temporarilyChangeCopyButtonText(
            copyButton
        );

    } catch (error) {
        console.error(
            "ページURLのコピーに失敗しました。",
            error
        );

        showShareCopyMessage(
            copyButton,
            "URLをコピーできませんでした。",
            true
        );

    } finally {
        copyButton.disabled = false;
    }
}


/**
 * テキストをクリップボードへコピーする。
 *
 * Clipboard APIが利用できない場合は、
 * document.execCommandを使用する。
 *
 * @param {string} text
 * @returns {Promise<void>}
 */
async function writeTextToClipboard(
    text
) {
    if (
        navigator.clipboard
        && window.isSecureContext
    ) {
        await navigator.clipboard.writeText(
            text
        );

        return;
    }

    copyTextWithFallback(
        text
    );
}


/**
 * Clipboard APIが利用できない環境向けの
 * フォールバックコピー処理。
 *
 * @param {string} text
 */
function copyTextWithFallback(
    text
) {
    const textArea = document.createElement(
        "textarea"
    );

    textArea.value = text;

    /*
     * 画面外へ配置し、
     * ページのスクロールを防止する。
     */
    textArea.style.position = "fixed";
    textArea.style.top = "0";
    textArea.style.left = "-9999px";
    textArea.style.opacity = "0";

    textArea.setAttribute(
        "readonly",
        ""
    );

    document.body.appendChild(
        textArea
    );

    textArea.focus();
    textArea.select();

    const copied = document.execCommand(
        "copy"
    );

    document.body.removeChild(
        textArea
    );

    if (!copied) {
        throw new Error(
            "フォールバックコピーに失敗しました。"
        );
    }
}


/**
 * URLコピーボタンの表示を一時的に変更する。
 *
 * @param {HTMLButtonElement} copyButton
 */
function temporarilyChangeCopyButtonText(
    copyButton
) {
    const originalText = (
        copyButton.dataset.originalText
        || copyButton.textContent.trim()
        || "URLをコピー"
    );

    copyButton.dataset.originalText =
        originalText;

    copyButton.textContent =
        "コピーしました";

    window.setTimeout(
        function () {
            copyButton.textContent =
                originalText;
        },
        2000
    );
}


/**
 * URLコピー結果のメッセージを表示する。
 *
 * @param {HTMLButtonElement} copyButton
 * @param {string} message
 * @param {boolean} isError
 */
function showShareCopyMessage(
    copyButton,
    message,
    isError
) {
    const shareSection = copyButton.closest(
        ".share-section"
    );

    if (!shareSection) {
        return;
    }

    const messageElement =
        shareSection.querySelector(
            ".share-copy-message"
        );

    if (!messageElement) {
        return;
    }

    messageElement.textContent =
        message;

    messageElement.classList.toggle(
        "is-error",
        Boolean(isError)
    );

    window.setTimeout(
        function () {
            /*
             * 新しいメッセージに更新されている場合は
             * 消さない。
             */
            if (
                messageElement.textContent
                === message
            ) {
                messageElement.textContent = "";

                messageElement.classList.remove(
                    "is-error"
                );
            }
        },
        3000
    );
}