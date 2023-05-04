import React, { useState, useRef, useEffect } from 'react';
import Stack from 'react-bootstrap/Stack';
import Table from 'react-bootstrap/Table';
import Card from 'react-bootstrap/Card';
import Tooltip from 'react-bootstrap/Tooltip';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import * as Icon from 'react-bootstrap-icons';
import * as CardFuncs from './CardFuncs.js'

export default function JmxCard(props) {
    const [container, ] = useState(props.container);
    const [focus, ] = useState(props.focus);

    const myRef = useRef(null);

    useEffect(() => {
        if (focus)
            myRef.current.scrollIntoView();
    });

    const showDesc = (
        <Tooltip id="objectDesc">{container.desc ? container.desc : "no description"}</Tooltip>
    )

    const renderUserDefined = (container) => {
        if (!container.user_defined)
            return <div></div>

        return (
            Object.keys(container.user_defined).map((x, key) =>
                <tr key={'user-defined-param'+key}>
                    <td>{x}</td>
                    <td>{container.user_defined[x]}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showJmxUserDefinedPlot(container, x, x)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
            )
        )
    }

    return (
        <Card ref={myRef} border="primary" className="shadow p-3 mb-5 bg-white rounded">
          <Card.Body>
            <Card.Title>
                <Stack direction="horizontal" gap={3}>
                <div className="led-container ">
                    <div className={CardFuncs.getContainerLEDStyle(container)}></div>
                </div>
                <OverlayTrigger placement="top" overlay={showDesc}>
                    <div className="cardtitle me-auto text-start">
                        {container.friendlyName}
                    </div>
                </OverlayTrigger>
                { container.src_update_available && <div>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipSrcUpdateAvailable}><Icon.Lightning style={{color:"#00FF00"}}/></OverlayTrigger>
                    </div>
                }
                <div className="vr" />
                <div><span style={{cursor:"pointer"}} onClick={() => props.showJmxStatusTimeseries(container)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipAvailGraph}><Icon.BarChart/></OverlayTrigger>
                    </span>
                </div>
                { container.panel &&
                    <div><span style={{cursor:"pointer"}} onClick={() => CardFuncs.openLink(container.panel)}>
                        <OverlayTrigger placement="top" overlay={CardFuncs.tooltipOpenLink}><Icon.ArrowBarUp/></OverlayTrigger>
                        </span>
                    </div>
                }
                { container.src &&
                    <div><span style={{cursor:"pointer"}} onClick={() => CardFuncs.openLink(container.src)}>
                        <OverlayTrigger placement="top" overlay={CardFuncs.tooltipOpenLinkToSourceCode}><Icon.CardHeading/></OverlayTrigger>
                        </span>
                    </div>
                }
                </Stack>
            </Card.Title>
                <Table className="statstable">
                <tbody>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsUptime}><Icon.Clock/></OverlayTrigger></td><td>{CardFuncs.formatSeconds(container.stats?.uptime_seconds)}</td>
                    <td><span style={{cursor:"pointer"}} onClick={() => props.showJmxPlot(container, 'uptime_seconds', 'Uptime [s]')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsCPU}><Icon.Cpu/></OverlayTrigger></td><td>{CardFuncs.formatPercentage(container.stats?.cpu_usage_percent)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showJmxPlot(container, 'cpu_usage_percent', 'CPU usage [%]')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsRAM}><Icon.Memory/></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.memory_usage_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showJmxPlot(container, 'memory_usage_bytes', 'Memory usage [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipNumClasses}><Icon.Puzzle/></OverlayTrigger></td><td>{container.stats?.num_classes}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showJmxPlot(container, 'num_classes', 'Num classes')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipNumThreads}><Icon.Grid/></OverlayTrigger></td><td>{container.stats?.num_threads}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showJmxPlot(container, 'num_threads', 'Num threads')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                </tbody>
                </Table>
                <Table className="statstable">
                <tbody>
                {renderUserDefined(container)}
                </tbody>
                </Table>
          </Card.Body>
        </Card>
    )
}