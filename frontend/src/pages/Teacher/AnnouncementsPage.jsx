import React, { useEffect, useState } from "react";
import { fetchMyClasses, sendNotice, fetchMyNotices } from "../../api/api";
import Loader from "../../components/common/loader";

export default function AnnouncementsPage() {
  const [notices, setNotices] = useState([]);
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Form State
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [targetClass, setTargetClass] = useState(""); // Empty = All my classes
  const [sending, setSending] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [classesRes, noticesRes] = await Promise.all([
        fetchMyClasses(),
        fetchMyNotices()
      ]);
      setClasses(classesRes.data || []);
      setNotices(noticesRes.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handlePost = async (e) => {
    e.preventDefault();
    if(!title || !content) return;

    setSending(true);
    try {
      await sendNotice({
        title,
        content,
        target_classroom_ids: targetClass ? [targetClass] : [], // Send to one or empty for generic
      });
      alert("Notice Sent Successfully!");
      setTitle("");
      setContent("");
      loadData(); // Refresh list
    } catch (err) {
      alert("Failed to send notice.");
    } finally {
      setSending(false);
    }
  };

  if(loading) return <Loader />;

  return (
    <div className="p-6 bg-gray-50 min-h-screen grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column: Create Notice */}
        <div className="lg:col-span-1">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 sticky top-6">
                <h2 className="text-xl font-bold text-gray-800 mb-4">Create Announcement</h2>
                <form onSubmit={handlePost} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-600 mb-1">Title</label>
                        <input 
                            className="w-full border rounded p-2 focus:ring-2 focus:ring-purple-500 outline-none"
                            placeholder="e.g. Exam Schedule"
                            value={title}
                            onChange={e => setTitle(e.target.value)}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-600 mb-1">Target Class (Optional)</label>
                        <select 
                            className="w-full border rounded p-2"
                            value={targetClass}
                            onChange={e => setTargetClass(e.target.value)}
                        >
                            <option value="">All My Classes</option>
                            {classes.map(c => <option key={c._id} value={c._id}>{c.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-600 mb-1">Message</label>
                        <textarea 
                            className="w-full border rounded p-2 h-32 resize-none focus:ring-2 focus:ring-purple-500 outline-none"
                            placeholder="Write your message here..."
                            value={content}
                            onChange={e => setContent(e.target.value)}
                        />
                    </div>
                    <button 
                        type="submit" 
                        disabled={sending}
                        className="w-full bg-purple-600 text-white py-2 rounded font-bold hover:bg-purple-700 transition disabled:bg-purple-300"
                    >
                        {sending ? "Posting..." : "Post Notice"}
                    </button>
                </form>
            </div>
        </div>

        {/* Right Column: History */}
        <div className="lg:col-span-2">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Sent History</h2>
            {notices.length === 0 ? (
                <p className="text-gray-400 italic">No notices sent yet.</p>
            ) : (
                <div className="space-y-4">
                    {notices.map((notice) => (
                        <div key={notice._id} className="bg-white p-5 rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition">
                            <div className="flex justify-between items-start">
                                <h3 className="font-bold text-lg text-gray-800">{notice.title}</h3>
                                <span className="text-xs text-gray-400">{new Date(notice.created_at).toDateString()}</span>
                            </div>
                            <p className="text-gray-600 mt-2 text-sm whitespace-pre-wrap">{notice.content}</p>
                            <div className="mt-3 pt-3 border-t flex justify-between items-center">
                                <span className="text-xs bg-purple-50 text-purple-700 px-2 py-1 rounded">
                                    {notice.target_classroom_ids?.length > 0 ? "Specific Class" : "General Notice"}
                                </span>
                                <span className="text-xs text-gray-400">Posted by You</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    </div>
  );
}
