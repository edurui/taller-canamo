use std::{
    io,
    process::{Child, Command, ExitStatus},
};

/// Own the complete sidecar process tree. PyInstaller onefile starts a second
/// process; killing only its bootstrapper can otherwise leave SQLite open.
pub(crate) struct ManagedChild {
    pub child: Child,
    terminated: bool,
    #[cfg(windows)]
    job: std::os::windows::io::OwnedHandle,
}

impl ManagedChild {
    pub fn spawn(command: &mut Command) -> io::Result<Self> {
        #[cfg(windows)]
        return windows::spawn(command);
        #[cfg(not(windows))]
        {
            #[cfg(target_os = "linux")]
            {
                use std::os::unix::process::CommandExt;
                let parent = std::process::id() as libc::pid_t;
                command.process_group(0);
                // SAFETY: only async-signal-safe syscalls run between fork and exec.
                unsafe {
                    command.pre_exec(move || {
                        if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                            return Err(io::Error::last_os_error());
                        }
                        if libc::getppid() != parent {
                            libc::_exit(1);
                        }
                        Ok(())
                    });
                }
            }
            Ok(Self {
                child: command.spawn()?,
                terminated: false,
            })
        }
    }

    pub fn terminate(&mut self) -> io::Result<ExitStatus> {
        if self.terminated {
            return self.child.wait();
        }
        self.terminated = true;
        #[cfg(windows)]
        {
            use std::os::windows::io::AsRawHandle;
            // SAFETY: job is an owned live handle and contains only our sidecar.
            unsafe {
                windows_sys::Win32::System::JobObjects::TerminateJobObject(
                    self.job.as_raw_handle(),
                    1,
                );
            }
        }
        #[cfg(target_os = "linux")]
        // SAFETY: the child was created in its own process group with this PID.
        unsafe {
            libc::kill(-(self.child.id() as i32), libc::SIGKILL);
        }
        let _ = self.child.kill();
        self.child.wait()
    }
}

impl Drop for ManagedChild {
    fn drop(&mut self) {
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.terminate();
        }
    }
}

#[cfg(windows)]
mod windows {
    use super::*;
    use std::{
        mem::{size_of, zeroed},
        os::windows::{
            io::{AsRawHandle, FromRawHandle, OwnedHandle},
            process::CommandExt,
        },
        ptr::null,
    };
    use windows_sys::Win32::{
        Foundation::{HANDLE, INVALID_HANDLE_VALUE},
        System::{
            Diagnostics::ToolHelp::{
                CreateToolhelp32Snapshot, Thread32First, Thread32Next, TH32CS_SNAPTHREAD,
                THREADENTRY32,
            },
            JobObjects::{
                AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
                SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            },
            Threading::{
                OpenThread, ResumeThread, CREATE_NO_WINDOW, CREATE_SUSPENDED, THREAD_SUSPEND_RESUME,
            },
        },
    };

    fn owned(raw: HANDLE) -> io::Result<OwnedHandle> {
        if raw.is_null() || raw == INVALID_HANDLE_VALUE {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: these handles are newly created and ownership is transferred once.
        Ok(unsafe { OwnedHandle::from_raw_handle(raw) })
    }

    pub fn spawn(command: &mut Command) -> io::Result<ManagedChild> {
        // SAFETY: null means default security, unnamed non-inheritable job.
        let job = owned(unsafe { CreateJobObjectW(null(), null()) })?;
        // SAFETY: the Win32 structure is plain data; size and pointer match its type.
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { zeroed() };
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if unsafe {
            SetInformationJobObject(
                job.as_raw_handle(),
                JobObjectExtendedLimitInformation,
                (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        // Suspended start prevents the PyInstaller bootstrapper creating a child
        // before the Job Object owns it. Closing the parent kills all descendants.
        command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED);
        let child = command.spawn()?;
        let mut process = ManagedChild {
            child,
            job,
            terminated: false,
        };
        if unsafe {
            AssignProcessToJobObject(process.job.as_raw_handle(), process.child.as_raw_handle())
        } == 0
        {
            let error = io::Error::last_os_error();
            let _ = process.terminate();
            return Err(error);
        }
        if let Err(error) = resume_initial_thread(process.child.id()) {
            let _ = process.terminate();
            return Err(error);
        }
        Ok(process)
    }

    fn resume_initial_thread(pid: u32) -> io::Result<()> {
        // std's ChildExt::main_thread_handle is unstable. Enumerate the sole
        // thread of our suspended child using the supported Win32 API instead.
        let snapshot = owned(unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) })?;
        let mut entry: THREADENTRY32 = unsafe { zeroed() };
        entry.dwSize = size_of::<THREADENTRY32>() as u32;
        let mut has_entry = unsafe { Thread32First(snapshot.as_raw_handle(), &mut entry) };
        while has_entry != 0 {
            if entry.th32OwnerProcessID == pid {
                let thread =
                    owned(unsafe { OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID) })?;
                if unsafe { ResumeThread(thread.as_raw_handle()) } == u32::MAX {
                    return Err(io::Error::last_os_error());
                }
                return Ok(());
            }
            has_entry = unsafe { Thread32Next(snapshot.as_raw_handle(), &mut entry) };
        }
        Err(io::Error::other(
            "No se encuentra el hilo del servicio auxiliar",
        ))
    }
}
