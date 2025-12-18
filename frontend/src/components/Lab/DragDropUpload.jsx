import React, { useState, useRef } from 'react';
import { UploadCloud, FileCode, X, CheckCircle2, AlertCircle } from 'lucide-react';
import { cn } from '../../lib/utils';

const DragDropUpload = ({ onUpload, className }) => {
    const [isDragging, setIsDragging] = useState(false);
    const [file, setFile] = useState(null);
    const [uploadStatus, setUploadStatus] = useState('idle'); // idle, uploading, success, error
    const fileInputRef = useRef(null);

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        const droppedFile = e.dataTransfer.files[0];
        validateAndSetFile(droppedFile);
    };

    const handleFileSelect = (e) => {
        const selectedFile = e.target.files[0];
        validateAndSetFile(selectedFile);
    };

    const validateAndSetFile = (selectedFile) => {
        if (!selectedFile) return;
        // Simple validation context
        const validExtensions = ['.pkl', '.h5', '.onnx', '.py', '.json'];
        const isValid = validExtensions.some(ext => selectedFile.name.endsWith(ext));

        if (isValid) {
            setFile(selectedFile);
            setUploadStatus('idle');
        } else {
            setUploadStatus('error');
            setFile(null);
        }
    };

    const handleUpload = async () => {
        if (!file || !onUpload) return;
        setUploadStatus('uploading');

        try {
            // Call the actual upload function passed from parent
            await onUpload(file);
            setUploadStatus('success');

            // Reset after success
            setTimeout(() => {
                setFile(null);
                setUploadStatus('idle');
            }, 2000);
        } catch (error) {
            console.error('Upload failed:', error);
            setUploadStatus('error');
            // Reset error state after 3 seconds
            setTimeout(() => {
                setUploadStatus('idle');
            }, 3000);
        }
    };

    return (
        <div className={cn("relative group", className)}>
            {/* Hidden Input */}
            <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                className="hidden"
                accept=".pkl,.h5,.onnx,.py,.json"
            />

            {/* Drop Zone */}
            <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                    "relative overflow-hidden rounded-xl border-2 border-dashed transition-all duration-300 cursor-pointer p-8 flex flex-col items-center justify-center min-h-[160px]", // Reduced height
                    // Default State (Light Theme)
                    "bg-slate-50 border-slate-300 hover:bg-purple-50 hover:border-purple-300",
                    // Dragging State
                    isDragging && "bg-purple-100 border-purple-500 scale-[1.02] shadow-xl shadow-purple-200",
                    // Success State
                    uploadStatus === 'success' && "border-emerald-500 bg-emerald-50",
                    // Error State
                    uploadStatus === 'error' && "border-red-500 bg-red-50"
                )}
            >
                {/* Background Glow Effect */}
                {/* <div className="absolute inset-0 bg-gradient-to-br from-purple-500/5 to-blue-500/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" /> */}

                {/* Content Logic */}
                {uploadStatus === 'success' ? (
                    <div className="text-center animate-in fade-in zoom-in duration-300">
                        <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-3 text-emerald-600">
                            <CheckCircle2 className="w-6 h-6" />
                        </div>
                        <h3 className="text-emerald-700 font-bold mb-1">Upload Complete</h3>
                        <p className="text-slate-500 text-xs">{file?.name}</p>
                    </div>
                ) : uploadStatus === 'error' ? (
                    <div className="text-center animate-in fade-in zoom-in duration-300">
                        <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-3 text-red-600">
                            <AlertCircle className="w-6 h-6" />
                        </div>
                        <h3 className="text-red-700 font-bold mb-1">Upload Failed</h3>
                        <p className="text-slate-500 text-xs">Please try again</p>
                        <button
                            onClick={(e) => { e.stopPropagation(); setUploadStatus('idle'); setFile(null); }}
                            className="mt-3 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded-lg transition-colors"
                        >
                            Try Again
                        </button>
                    </div>
                ) : !file ? (
                    <>
                        <div className={cn(
                            "w-12 h-12 rounded-xl flex items-center justify-center mb-4 transition-all duration-300",
                            isDragging ? "bg-purple-500 text-white shadow-lg shadow-purple-200" : "bg-white text-slate-400 shadow-sm border border-slate-200 group-hover:text-purple-500 group-hover:border-purple-200"
                        )}>
                            <UploadCloud className="w-6 h-6" />
                        </div>
                        <h3 className="text-slate-700 font-bold mb-1">Upload Model File</h3>
                        <p className="text-slate-500 text-xs mb-4">Drag & drop or Click to browse</p>
                        <div className="flex gap-2">
                            {['.PKL', '.ONNX', '.H5'].map(ext => (
                                <span key={ext} className="px-2 py-1 bg-white rounded text-[10px] text-slate-500 font-mono border border-slate-200 shadow-sm">
                                    {ext}
                                </span>
                            ))}
                        </div>
                    </>
                ) : (
                    // File Selected State
                    <div className="flex flex-col items-center w-full animate-in fade-in slide-in-from-bottom-2">
                        <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center mb-3 text-purple-600 border border-purple-200">
                            <FileCode className="w-6 h-6" />
                        </div>
                        <p className="text-slate-900 font-medium mb-1 truncate max-w-[200px]">{file.name}</p>
                        <p className="text-slate-500 text-xs mb-4">{(file.size / 1024).toFixed(1)} KB</p>

                        <div className="flex gap-3">
                            <button
                                onClick={(e) => { e.stopPropagation(); setFile(null); }}
                                className="px-4 py-2 bg-white hover:bg-slate-50 text-slate-600 text-xs font-bold rounded-lg transition-colors border border-slate-200 shadow-sm"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={(e) => { e.stopPropagation(); handleUpload(); }}
                                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold rounded-lg shadow-lg shadow-purple-200 flex items-center gap-2 transition-all"
                            >
                                {uploadStatus === 'uploading' ? (
                                    <>
                                        <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                        Uploading...
                                    </>
                                ) : (
                                    <>
                                        <UploadCloud className="w-3 h-3" />
                                        Upload
                                    </>
                                )}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default DragDropUpload;
