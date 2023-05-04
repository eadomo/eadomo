import Tooltip from 'react-bootstrap/Tooltip';

export const formatSeconds = (seconds) => {
    if (seconds === null || seconds === undefined) return '-'

    seconds = Number(seconds);
    var d = Math.floor(seconds / (3600*24));
    var h = Math.floor(seconds % (3600*24) / 3600);
    var m = Math.floor(seconds % 3600 / 60);
    var s = Math.floor(seconds % 60);

    var dDisplay = d > 0 ? d + (d === 1 ? " d " : " d ") : "";
    var hDisplay = h > 0 ? h + (h === 1 ? " h " : " h ") : "";
    var mDisplay = m > 0 ? m + (m === 1 ? " m " : " m ") : "";
    var sDisplay = s > 0 ? s + (s === 1 ? " s" : " s") : "";
    return dDisplay + hDisplay + mDisplay + sDisplay;
}

export const formatPercentage = (num) => {
    if (num === null || num === undefined) return '-'

    return Number(num).toFixed(2) + ' %'
}

export const formatBytes = (bytes, decimals=2) => {
    if (bytes === null || bytes === undefined) return '-'

    if (!+bytes) return '0 Bytes'

    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

    const i = Math.floor(Math.log(bytes) / Math.log(k))

    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
}

export const getContainerLEDStyle = (container) => {
    if (container.status !== "OK")
        return "led-red"

    if (container.last_failure != null) {
        const lastFailure = new Date(container.last_failure);

        const dateDiff = new Date() - lastFailure;

        if (dateDiff < 1000 * 60 * 60)
            return "led-yellow";
    }

    return "led-green";
}

export const openLink = (url) => {
    window.open(url, '_blank', 'noreferrer')
}

export const tooltipShowLog = (
  <Tooltip id="tooltipShowLog">Show log</Tooltip>
)
export const tooltipOpenLink = (
  <Tooltip id="tooltipOpenControlPanelLink">Open control panel</Tooltip>
)
export const tooltipOpenLinkToSourceCode = (
  <Tooltip id="tooltipOpenSrcLink">Go to source code repository</Tooltip>
)
export const tooltipAvailGraph = (
  <Tooltip id="tooltipAvailGraph">Show availability graph</Tooltip>
)
export const tooltipStatsUptime = (
  <Tooltip id="tooltipStatsUptime">Uptime</Tooltip>
)
export const tooltipStatsCPU = (
  <Tooltip id="tooltipStatsCPU">CPU load</Tooltip>
)
export const tooltipStatsRAM = (
  <Tooltip id="tooltipStatsRAM">RAM usage</Tooltip>
)
export const tooltipStatsDisk = (
  <Tooltip id="tooltipStatsDisk">Disk usage</Tooltip>
)
export const tooltipStatsDiskWriten =(
  <Tooltip id="tooltipDiskWritten">Written to disk</Tooltip>
)
export const tooltipStatsDiskRead = (
  <Tooltip id="tooltipDiskRead">Read from disk</Tooltip>
)
export const tooltipStatsNetworkSent = (
  <Tooltip id="tooltipNetworkSent">Sent via network</Tooltip>
)
export const tooltipStatsNetworkRcvd = (
  <Tooltip id="tooltipNetworkRcvd">Received via network</Tooltip>
)
export const tooltipUpdateAvailable = (
  <Tooltip id="tooltipUpdateAvailable">Image update available</Tooltip>
)
export const tooltipSrcUpdateAvailable = (
  <Tooltip id="tooltipSrcUpdateAvailable">Source code updated</Tooltip>
)
export const tooltipTimeseries = (
  <Tooltip id="tooltipTimeseries">Show timeseries</Tooltip>
)
export const tooltipNumClasses = (
  <Tooltip id="tooltipNumClasses">Number of classes</Tooltip>
)
export const tooltipNumThreads = (
  <Tooltip id="tooltipNumThreads">Number of threads</Tooltip>
)
export const tooltipNumPids = (
  <Tooltip id="tooltipNumPids">Number of PIDs</Tooltip>
)
export const tooltipShowEnvs = (
  <Tooltip id="tooltipShowEnvs">Show environment variables</Tooltip>
)
export const tooltipShowInspect = (
  <Tooltip id="tooltipShowInspect">Inspect container</Tooltip>
)
export const tooltipShowImageInspect = (
  <Tooltip id="tooltipShowImageInspect">Inspect image</Tooltip>
)
export const tooltipRestartCont = (
  <Tooltip id="tooltipRestartCont">Restart container</Tooltip>
)

