import React, { useEffect, useRef } from 'react';

const MatrixTerminal = ({ logs }) => {
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    return (
        <div className="bg-black border border-slate-800 rounded-lg p-4 font-mono text-xs h-64 overflow-hidden flex flex-col shadow-inner">
            <div className="flex items-center justify-between mb-2 pb-2 border-b border-white/10 opacity-50">
                <span className="uppercase text-[10px] tracking-widest text-green-500 font-bold">System Log</span>
                <div className="flex space-x-1">
                    <div className="w-2 h-2 rounded-full bg-red-500/50" />
                    <div className="w-2 h-2 rounded-full bg-yellow-500/50" />
                    <div className="w-2 h-2 rounded-full bg-green-500/50" />
                </div>
            </div>

            <div className="flex-1 overflow-y-auto noscrollbar space-y-1">
                {logs.map((log, i) => (
                    <div key={i} className="break-words">
                        <span className="text-slate-600 mr-2">[{log.time}]</span>
                        <span className={log.color || "text-green-500"}>
                            <span className="font-bold mr-2">{log.prefix}:</span>
                            {log.message}
                        </span>
                    </div>
                ))}
                <div ref={bottomRef} />
            </div>
        </div>
    );
};

export default MatrixTerminal;
